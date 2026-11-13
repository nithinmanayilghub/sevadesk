# deploy.sh reads this with "terraform output -raw url" and checks /api/v1/hello on it.
output "url" {
  description = "Public staging address (HTTP only: no domain, so no TLS certificate)."
  value       = "http://${aws_lb.main.dns_name}"
}
