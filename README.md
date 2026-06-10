WarehouseMS — Smart Warehouse Management System
A SaaS platform for managing and monitoring storage locations, suitable for both home and commercial use.

## Setup

Copy `.env.example` to `.env` and fill in your values before running:
```bash
cp .env.example .env
docker compose up -d
```
Features
Inventory Management

Create boxes and items with unique codes (B001, I001)
Add images to boxes and items
Manage quantities
Fast search by name, tag, category and location
Filter by location, category and tag
Gallery and list view toggle

QR Codes

Generate a QR code for every box
Scan to view box contents without opening it

User Management

Full role-based permissions: Admin, Manager, Contributor, Viewer
Invite users with a unique join code
Approve or reject join requests
Support for multiple Workspaces per user
Switch between workspaces from the sidebar

Tracking & Monitoring

Full change history for every box and item
Track who last modified each item
Real-time sync between users

Data Export

Export to CSV
Export to Excel

## Secrets & Configuration

### Local Development

Copy the example and fill in your values:
```bash
cp .env.example .env
```

For MySQL Helm chart, create a local values file (not committed to Git):
```bash
cp mysql/helm/values-local.example.yaml mysql/helm/values-local.yaml
```
Then edit `values-local.yaml` with your passwords.

### Production (Kubernetes)

Create a Kubernetes Secret before deploying:
```bash
kubectl create secret generic warehouse-mysql-secret \
  --from-literal=mysql-root-password="your-root-password" \
  --from-literal=mysql-password="your-password"
```