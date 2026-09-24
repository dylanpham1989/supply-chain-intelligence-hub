# Left on the local backend on purpose, because this environment is never
# applied. What it would be:
#
# terraform {
#   backend "s3" {
#     bucket         = "scih-tfstate"
#     key            = "staging/terraform.tfstate"
#     region         = "eu-west-1"
#     encrypt        = true
#     dynamodb_table = "scih-tflock"
#   }
# }
#
# The lock table is the part that matters. Without it two people running apply
# at the same time write over each other's state, and the recovery is manual
# surgery on a JSON file that describes real infrastructure.
