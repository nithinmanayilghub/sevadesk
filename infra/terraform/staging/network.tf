# The network: one private address space (VPC), two public subnets, and three security groups.
# No NAT gateway (it costs about $1/day): the containers get public IPs and reach GHCR directly.
#
# Security groups are firewalls around resources. Who may talk to whom:
#   internet --80--> ALB --3000/8000--> tasks (containers) --5432/6379--> data (RDS, Valkey)

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true # containers find RDS and Valkey by name
  tags                 = { Name = "sevadesk-staging" }
}

# The door between the VPC and the internet.
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "sevadesk-staging" }
}

# One subnet in EVERY zone (Mumbai has 3). Small machine types sell out per zone; with a subnet
# everywhere, RDS picks a zone that still has space. (ALB, RDS and ElastiCache need at least two zones.)
resource "aws_subnet" "public" {
  count                   = length(data.aws_availability_zones.available.names)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index) # 10.40.0.0/24, 10.40.1.0/24, ...
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "sevadesk-staging-public-${count.index}" }
}

# All traffic to the outside world goes through the internet gateway.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "sevadesk-staging-public" }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- Security group: the load balancer ---
resource "aws_security_group" "alb" {
  name        = "sevadesk-staging-alb"
  description = "SevaDesk staging ALB: HTTP from the internet"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_from_internet" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from anywhere"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_anywhere" {
  security_group_id = aws_security_group.alb.id
  description       = "Forward requests to the tasks"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --- Security group: the app containers (frontend, backend, worker) ---
resource "aws_security_group" "tasks" {
  name        = "sevadesk-staging-tasks"
  description = "SevaDesk staging containers: only the ALB may connect"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_frontend_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "Next.js, from the ALB only"
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_backend_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "FastAPI, from the ALB only"
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  referenced_security_group_id = aws_security_group.alb.id
}

# Containers may call out: pull images from GHCR, reach RDS/Valkey, and later the AI APIs.
resource "aws_vpc_security_group_egress_rule" "tasks_to_anywhere" {
  security_group_id = aws_security_group.tasks.id
  description       = "Outbound: GHCR, RDS, Valkey, external APIs"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --- Security group: the data stores (RDS and Valkey) ---
# No egress rule: databases only answer; they never start a connection.
resource "aws_security_group" "data" {
  name        = "sevadesk-staging-data"
  description = "SevaDesk staging RDS and Valkey: only the containers may connect"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "data_postgres_from_tasks" {
  security_group_id            = aws_security_group.data.id
  description                  = "Postgres, from the containers only"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.tasks.id
}

resource "aws_vpc_security_group_ingress_rule" "data_valkey_from_tasks" {
  security_group_id            = aws_security_group.data.id
  description                  = "Valkey, from the containers only"
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
  referenced_security_group_id = aws_security_group.tasks.id
}
