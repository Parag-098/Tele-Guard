locals {
  name      = "teleguard"
  partition = data.aws_partition.current.partition
  account   = data.aws_caller_identity.current.account_id
  arn       = "arn:${local.partition}"
  buckets   = toset(["artifacts", "backups", "releases"])
  registry  = "${local.account}.dkr.ecr.${var.region}.${data.aws_partition.current.dns_suffix}"
}

resource "aws_vpc" "demo" {
  cidr_block           = "10.29.0.0/24"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = local.name }
}
resource "aws_internet_gateway" "demo" {
  vpc_id = aws_vpc.demo.id
}
resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.29.0.0/26"
  availability_zone = var.availability_zone
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
resource "aws_security_group" "host" {
  name        = "${local.name}-https"
  description = "Caddy public traffic only; administration uses Systems Manager."
  vpc_id      = aws_vpc.demo.id
}
resource "aws_vpc_security_group_ingress_rule" "caddy" {
  for_each          = { http = [80, "tcp"], https = [443, "tcp"], http3 = [443, "udp"] }
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = each.value[0]
  to_port           = each.value[0]
  ip_protocol       = each.value[1]
}
resource "aws_vpc_security_group_egress_rule" "web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = tonumber(each.key)
  to_port           = tonumber(each.key)
  ip_protocol       = "tcp"
}

resource "aws_ebs_volume" "data" {
  availability_zone = aws_subnet.public.availability_zone
  encrypted         = true
  size              = var.data_volume_gib
  type              = "gp3"
  tags              = { Name = "${local.name}-persistent" }
  lifecycle {
    prevent_destroy = true
  }
}
resource "aws_instance" "host" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.host.id]
  iam_instance_profile        = aws_iam_instance_profile.host.name
  user_data_base64 = base64encode(templatefile("${path.module}/bootstrap.sh.tftpl", {
    compose_version = var.compose_version
    compose_sha256  = var.compose_sha256
    volume_serial   = replace(aws_ebs_volume.data.id, "-", "")
  }))
  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 24
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  credit_specification {
    cpu_credits = "standard"
  }
  tags       = { Name = local.name }
  depends_on = [aws_route_table_association.public, aws_iam_role_policy_attachment.ssm]
}
resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.host.id
}
resource "aws_eip" "host" {
  domain   = "vpc"
  instance = aws_instance.host.id
}

resource "aws_s3_bucket" "storage" {
  for_each = local.buckets
  bucket   = "${local.name}-${each.key}-${local.account}-${var.region}"
  lifecycle {
    prevent_destroy = true
  }
}
resource "aws_s3_bucket_public_access_block" "storage" {
  for_each                = aws_s3_bucket.storage
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_versioning" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_policy" "tls" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [each.value.arn, "${each.value.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.storage["backups"].id
  rule {
    id     = "daily-backup-retention"
    status = "Enabled"
    filter {
      prefix = "postgres/"
    }
    expiration {
      days = 30
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  depends_on = [aws_s3_bucket_versioning.storage]
}
resource "aws_ecr_repository" "app" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}
