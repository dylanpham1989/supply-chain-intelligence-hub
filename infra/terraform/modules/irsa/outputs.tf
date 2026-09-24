output "role_arn" {
  description = "Goes on the ServiceAccount as eks.amazonaws.com/role-arn."
  value       = aws_iam_role.this.arn
}
