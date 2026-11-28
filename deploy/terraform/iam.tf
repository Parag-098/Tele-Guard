resource "aws_iam_role" "host" {
  name = "${local.name}-host"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
resource "aws_iam_instance_profile" "host" {
  name = aws_iam_role.host.name
  role = aws_iam_role.host.name
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "${local.arn}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "host" {
  name = "application-runtime"
  role = aws_iam_role.host.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"],
      Resource = [for repository in aws_ecr_repository.app : repository.arn] },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents"],
      Resource = "${aws_cloudwatch_log_group.app.arn}:*" },
      { Effect = "Allow", Action = "cloudwatch:PutMetricData", Resource = "*",
      Condition = { StringEquals = { "cloudwatch:namespace" = ["TeleGuard/Host", "TeleGuard/Operations"] } } },
      { Effect = "Allow", Action = ["ec2:DescribeTags", "ec2:DescribeVolumes"], Resource = "*" },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:AbortMultipartUpload"],
      Resource = ["${aws_s3_bucket.storage["artifacts"].arn}/mlflow/*", "${aws_s3_bucket.storage["artifacts"].arn}/datasets/*", "${aws_s3_bucket.storage["backups"].arn}/postgres/*"] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"],
      Resource = "${aws_s3_bucket.storage["releases"].arn}/bundles/*" },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"],
      Resource = "${aws_s3_bucket.storage["backups"].arn}/postgres/*" },
      { Effect = "Allow", Action = "s3:ListBucket", Resource = aws_s3_bucket.storage["artifacts"].arn,
      Condition = { StringLike = { "s3:prefix" = ["mlflow", "mlflow/*", "datasets", "datasets/*"] } } }
    ]
  })
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "release" {
  name = "${local.name}-github-release"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.github_oidc_provider_arn == null ? aws_iam_openid_connect_provider.github[0].arn : var.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:production"
      } }
    }]
  })
}
resource "aws_iam_role_policy" "release" {
  name = "publish-and-release"
  role = aws_iam_role.release.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken", "ssm:GetCommandInvocation"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload",
        "ecr:DescribeImages", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart"],
      Resource = [for repository in aws_ecr_repository.app : repository.arn] },
      { Effect = "Allow", Action = "s3:PutObject", Resource = "${aws_s3_bucket.storage["releases"].arn}/bundles/*",
      Condition = { StringEquals = { "s3:if-none-match" = "*" } } },
      { Effect = "Allow", Action = "ssm:SendCommand", Resource = [aws_instance.host.arn, aws_ssm_document.release.arn] }
    ]
  })
}

resource "aws_ssm_document" "release" {
  name            = "TeleGuard-DeployRelease"
  document_type   = "Command"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy a checksummed TeleGuard release bundle from the account release bucket."
    parameters = {
      revision = { type = "String", allowedPattern = "^[a-f0-9]{40}$" }
      checksum = { type = "String", allowedPattern = "^[a-f0-9]{64}$" }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "installAndDeploy"
      inputs = {
        timeoutSeconds = "840"
        runCommand = [
          "set -eu",
          "umask 077",
          "stage=$(mktemp -d)",
          "trap 'rm -rf -- \"$stage\"' EXIT",
          "aws s3 cp --only-show-errors --region ${var.region} s3://${aws_s3_bucket.storage["releases"].id}/bundles/{{ revision }}-{{ checksum }}.tar.gz \"$stage/release.tar.gz\"",
          "printf '%s  %s\\n' '{{ checksum }}' \"$stage/release.tar.gz\" | sha256sum --check --status",
          "tar --extract --gzip --file \"$stage/release.tar.gz\" --directory \"$stage\" --no-same-owner --no-same-permissions",
          "bash \"$stage/deploy/deploy-release.sh\" --install \"$stage\" '{{ revision }}' '{{ checksum }}'"
        ]
      }
    }]
  })
}
