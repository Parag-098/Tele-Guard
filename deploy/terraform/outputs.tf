output "public_ipv4" {
  value = aws_eip.host.public_ip
}
output "instance_id" {
  value = aws_instance.host.id
}
output "ecr_registry" {
  value = local.registry
}
output "release_role_arn" {
  value = aws_iam_role.release.arn
}
output "release_bucket" {
  value = aws_s3_bucket.storage["releases"].id
}
output "artifact_bucket" {
  value = aws_s3_bucket.storage["artifacts"].id
}
output "backup_bucket" {
  value = aws_s3_bucket.storage["backups"].id
}
output "deploy_document_name" {
  value = aws_ssm_document.release.name
}
