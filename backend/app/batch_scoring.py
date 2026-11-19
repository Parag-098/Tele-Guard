"""Vectorized, as-of-time scoring used for large versioned event imports."""

from collections import defaultdict
from math import asin, cos, radians, sin, sqrt

import numpy as np

from app.config import settings
from app.ml import model_feature_version, model_input


class BatchScoringState:
    def __init__(self):
        self.entity_subscribers = defaultdict(set)
        self.location_tokens = defaultdict(list)
        self.last_coordinates = {}

    def seed_context(self, rows):
        for row in sorted(rows, key=lambda item: item["event_time"]):
            subscriber = row["subscriber_id"]
            for field, kind in (("device_id", "device"), ("network_token", "network"), ("sim_id", "sim")):
                token = row.get(field)
                if token:
                    self.entity_subscribers[(kind, token)].add(subscriber)
            location = row.get("location_token")
            if location:
                tokens = self.location_tokens[subscriber]
                tokens.append(location)
                if len(tokens) > 100:
                    del tokens[:-100]
            if row.get("latitude") is not None and row.get("longitude") is not None:
                self.last_coordinates[subscriber] = (
                    float(row["latitude"]), float(row["longitude"]), _timestamp(row["event_time"])
                )

    def score(self, rows, feature_frame, champion, challenger=None, serving=None, scenario=None):
        serving = serving or {"mode": "champion"}
        scenario = scenario or {
            "max_speed_kmh": 900,
            "impossible_travel_minutes": 120,
            "risk_weight": 0.2,
            "unusual_location_min_history": 4,
            "scenario_rules": {},
        }
        champion_signals = _model_signals(champion, feature_frame)
        challenger_signals = _model_signals(challenger, feature_frame) if challenger else None
        outputs = []
        for index, row in enumerate(rows):
            sub = row["subscriber_id"]
            entities = [
                (kind, row.get(field))
                for field, kind in (("device_id", "device"), ("network_token", "network"), ("sim_id", "sim"))
                if row.get(field)
            ]
            linked = set()
            for kind, token in entities:
                linked.update(self.entity_subscribers[(kind, token)])
            linked.discard(sub)
            graph_score = min(len(linked) / 5, 1.0)
            for kind, token in entities:
                self.entity_subscribers[(kind, token)].add(sub)

            rules = []
            if row.get("event_type") in {"SIM_CHANGE", "DEVICE_CHANGE"}:
                rules.append("recent_identity_change")
            if row.get("event_type") == "CALL" and (row.get("duration_seconds") or 0) < 10:
                rules.append("short_call_pattern")
            rule_score = 1.0 if rules else 0.0
            location_score, findings = self._location_score(row, sub, scenario)
            context_weight = float(scenario.get("risk_weight", 0.2))

            champion_probability, champion_anomaly = champion_signals[index]
            selected_model = champion
            probability, anomaly = champion_probability, champion_anomaly
            observations = [(champion["version"], "champion", champion_probability)]
            if challenger_signals is not None and serving.get("mode") in {"shadow", "canary"}:
                challenger_probability, _ = challenger_signals[index]
                canary = serving.get("mode") == "canary" and (
                    int(row["event_id"].encode().hex()[:8], 16) % 100
                    < int(serving.get("canary_percent", 0))
                )
                observations.append((
                    challenger["version"], "canary" if canary else "shadow", challenger_probability
                ))
                if canary:
                    selected_model = challenger
                    probability, anomaly = challenger_signals[index]

            risk = float(np.clip(
                settings.risk_supervised_weight * probability
                + settings.risk_anomaly_weight * anomaly
                + settings.risk_graph_weight * graph_score
                + settings.risk_rule_weight * rule_score
                + context_weight * location_score,
                0,
                1,
            ))
            risk_band = "Critical" if risk >= 0.8 else "High" if risk >= 0.6 else "Medium" if risk >= 0.35 else "Low"
            evidence = [
                {"signal": "supervised_model", "value": round(probability, 3), "detail": "Supervised classifier probability; synthetic training data"},
                {"signal": "anomaly_detector", "value": round(anomaly, 3), "detail": "Isolation Forest normalized outlier score"},
                {"signal": "shared_entities", "value": round(graph_score, 3), "detail": f"{len(linked)} connected synthetic subscribers; weak evidence only"},
            ]
            evidence.extend({"signal": "rule", "value": name, "detail": "Versioned rule fired on event metadata"} for name in rules)
            evidence.append({"signal": "location_travel_scenario", "value": location_score,
                             "detail": "; ".join(item["detail"] for item in findings) if findings else "Location history checked; no configured concern found.",
                             "findings": findings})
            outputs.append({
                "event_id": row["event_id"],
                "model_version": selected_model["version"],
                "feature_version": model_feature_version(selected_model),
                "probability": probability,
                "anomaly_score": anomaly,
                "graph_score": graph_score,
                "rule_score": rule_score,
                "risk_score": risk,
                "risk_band": risk_band,
                "evidence": evidence,
                "observations": observations,
            })
        return outputs

    def _location_score(self, row, subscriber, config):
        findings = []
        prior_tokens = self.location_tokens[subscriber]
        lat, lon = row.get("latitude"), row.get("longitude")
        previous = self.last_coordinates.get(subscriber)
        if lat is not None and lon is not None and previous:
            prior_lat, prior_lon, prior_time = previous
            current_time = _timestamp(row["event_time"])
            minutes = (current_time - prior_time).total_seconds() / 60
            if 0 < minutes <= float(config["impossible_travel_minutes"]):
                lat1, lon1, lat2, lon2 = map(radians, [prior_lat, prior_lon, float(lat), float(lon)])
                dlat, dlon = lat2 - lat1, lon2 - lon1
                distance = 6371 * 2 * asin(sqrt(sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2))
                if distance / (minutes / 60) > float(config["max_speed_kmh"]):
                    findings.append({"code": "impossible_travel", "distance_km": round(distance, 1),
                                     "elapsed_minutes": round(minutes, 1),
                                     "detail": "Recorded coordinates imply travel beyond the configured speed limit."})
        location = row.get("location_token")
        if location and len(prior_tokens) >= int(config["unusual_location_min_history"]) and location not in prior_tokens:
            findings.append({"code": "unusual_geography", "detail": "Location token is new for this subscriber's available event history; review context before treating as suspicious."})
        for name, rule in config.get("scenario_rules", {}).items():
            if isinstance(rule, dict) and (
                rule.get("event_type") == row.get("event_type")
                or (rule.get("location_token") and rule.get("location_token") == location)
            ):
                findings.append({"code": "configured_scenario", "scenario": str(name)[:80],
                                 "detail": str(rule.get("description", "Configured event/location risk scenario"))[:240]})
        if location:
            prior_tokens.append(location)
            if len(prior_tokens) > 100:
                del prior_tokens[:-100]
        if lat is not None and lon is not None:
            self.last_coordinates[subscriber] = (float(lat), float(lon), _timestamp(row["event_time"]))
        risk = min(1.0, 0.8 if any(f["code"] == "impossible_travel" for f in findings)
                   else 0.35 if findings else 0.0)
        return risk, findings


def _model_signals(model, feature_frame):
    if model is None:
        return None
    classifier = model["model"]
    detector = model.get("anomaly_detector")
    if detector is None:
        raise RuntimeError("The trained model artifact has no fitted anomaly detector")
    compatible = model_input(model, feature_frame)
    probabilities = classifier.predict_proba(compatible)[:, 1]
    raw = detector.score_samples(compatible)
    anomalies = np.clip((-0.35 - raw) / 0.45, 0, 1)
    return list(zip(probabilities.astype(float), anomalies.astype(float)))


def _timestamp(value):
    from datetime import datetime, timezone
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
