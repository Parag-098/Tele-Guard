"""Catch missing or widened API role guards across the complete FastAPI surface."""

from fastapi.routing import APIRoute

from app.main import app
from app.security import current_user


EXPECTED_ROLE_GUARDS = {
    ("POST", "/api/auth/users"): {"Administrator"},
    ("GET", "/api/auth/users"): {"Administrator"},
    ("PATCH", "/api/auth/users/{username}"): {"Administrator"},
    ("POST", "/api/events"): {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer"},
    ("POST", "/api/events/upload-csv"): {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer"},
    ("POST", "/api/scenarios/generate"): {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer"},
    ("PATCH", "/api/incidents/{incident_id}"): {"Administrator", "Fraud Analyst", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/notes"): {"Administrator", "Fraud Analyst", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/actions"): {"Administrator", "Investigator"},
    ("POST", "/api/actions/{action_id}/reverse"): {"Administrator", "Investigator"},
    ("POST", "/api/models/train"): {"Administrator", "ML Engineer"},
    ("POST", "/api/datasets/seed"): {"Administrator"},
    ("POST", "/api/datasets/research-training"): {"Administrator", "ML Engineer"},
    ("POST", "/api/predictions/{event_id}/label"): {"Administrator", "Fraud Analyst", "Investigator"},
    ("POST", "/api/mlops/serving"): {"Administrator"},
    ("POST", "/api/mlops/scenarios"): {"Administrator"},
    ("POST", "/api/mlops/initialize"): {"Administrator"},
    ("POST", "/api/mlops/drift/simulate"): {"Administrator"},
    ("POST", "/api/mlops/drift/detect"): {"Administrator", "ML Engineer"},
    ("POST", "/api/mlops/retrain"): {"Administrator", "ML Engineer"},
    ("POST", "/api/mlops/compare"): {"Administrator", "ML Engineer"},
    ("POST", "/api/mlops/decisions/{candidate_version}"): {"Administrator"},
    ("POST", "/api/mlops/rollback"): {"Administrator"},
    ("POST", "/api/mlops/reset-demo"): {"Administrator"},
    ("GET", "/api/audit"): {"Administrator", "Auditor"},
    ("POST", "/api/predictions/{event_id}/adjudications"):
        {"Administrator", "Fraud Analyst", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/adjudications"):
        {"Administrator", "Fraud Analyst", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/merge"): {"Administrator", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/unmerge"): {"Administrator", "Investigator"},
    ("POST", "/api/incidents/{incident_id}/reopen"): {"Administrator", "Investigator"},
    ("GET", "/api/review/queue"): {"Administrator", "Fraud Analyst", "Investigator"},
    ("GET", "/api/analytics/impact"):
        {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer", "Auditor"},
    ("POST", "/api/simulator/runs"): {"Administrator", "ML Engineer"},
    ("POST", "/api/simulator/runs/{run_id}/{action}"): {"Administrator", "ML Engineer"},
}

PUBLIC_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/ready"),
    ("POST", "/api/auth/login"),
}


def _dependencies(route: APIRoute):
    pending = list(route.dependant.dependencies)
    seen = set()
    while pending:
        dependency = pending.pop()
        call = dependency.call
        if call in seen:
            continue
        seen.add(call)
        yield call
        pending.extend(dependency.dependencies)


def _api_routes():
    """Flatten router includes for FastAPI versions with deferred router entries."""
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        if isinstance(route, APIRoute):
            if route.path.startswith("/api/"):
                yield route
            continue
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(original_router.routes)


def _required_roles(call):
    if not hasattr(call, "__code__"):
        return None
    closure = getattr(call, "__closure__", None) or ()
    values = dict(zip(call.__code__.co_freevars, (cell.cell_contents for cell in closure)))
    roles = values.get("roles")
    return frozenset(roles) if isinstance(roles, tuple) and all(
        isinstance(role, str) for role in roles
    ) else None


def test_every_api_route_has_an_authentication_boundary():
    actual = set()
    for route in _api_routes():
        calls = set(_dependencies(route))
        for method in route.methods:
            key = (method, route.path)
            actual.add(key)
            if key in PUBLIC_ROUTES:
                assert current_user not in calls, f"public route unexpectedly requires a session: {key}"
            else:
                assert current_user in calls, f"API route has no authenticated principal: {key}"


def test_explicit_role_guards_match_the_reviewed_api_permission_matrix():
    actual = {}
    for route in _api_routes():
        calls = list(_dependencies(route))
        role_guards = [roles for call in calls if (roles := _required_roles(call))]
        for method in route.methods:
            key = (method, route.path)
            if role_guards:
                assert len(role_guards) == 1, f"multiple ambiguous role guards on {key}"
                actual[key] = set(role_guards[0])
    missing = {key: roles for key, roles in EXPECTED_ROLE_GUARDS.items() if key not in actual}
    unexpected = {key: roles for key, roles in actual.items() if key not in EXPECTED_ROLE_GUARDS}
    changed = {key: (EXPECTED_ROLE_GUARDS[key], actual[key]) for key in actual.keys() & EXPECTED_ROLE_GUARDS.keys()
               if actual[key] != EXPECTED_ROLE_GUARDS[key]}
    assert actual == EXPECTED_ROLE_GUARDS, (
        f"missing={missing}; unexpected={unexpected}; changed={changed}"
    )


def test_custom_job_owner_route_keeps_authenticated_ownership_policy():
    route = next(
        route for route in _api_routes() if route.path == "/api/jobs/{job_id}/control"
    )
    calls = set(_dependencies(route))
    assert current_user in calls
    assert not any(_required_roles(call) for call in calls)
