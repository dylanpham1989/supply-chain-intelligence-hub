output "endpoint" {
  value = aws_db_instance.this.address
}

output "security_group_id" {
  value = aws_security_group.this.id
}

output "master_secret_arn" {
  description = "Secrets Manager secret RDS manages for the master password."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
