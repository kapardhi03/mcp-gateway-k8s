# VPS runbook: TLS and exposure

Order matters. Each step has a row in `docs/requirements-trace.md` (VDOD-*).

Everything here targets the VPS, never the local cluster:

```
export KUBECONFIG=~/.kube/gw-prod.yaml
```

The tunnel must be open first:

```
gcloud compute ssh gw-prod --project=mcp-kb8 --zone=asia-south1-a \
  --tunnel-through-iap -- -N -L 16443:localhost:6443
```

## 1. cert-manager (VDOD-1)

Pinned, from the OCI registry, which cert-manager's docs call the source of truth.

```
helm install cert-manager oci://quay.io/jetstack/charts/cert-manager \
  --version v1.21.2 --namespace cert-manager --create-namespace \
  --set crds.enabled=true
```

## 2. ClusterIssuers (VDOD-2)

Set the ACME contact email first. It is a placeholder on purpose.

```
sed -i '' 's/ACME_EMAIL_PLACEHOLDER/you@example.com/' deploy/vps/clusterissuers.yaml
kubectl apply -f deploy/vps/clusterissuers.yaml
kubectl get clusterissuer
```

Both must report `READY=True` before going further.

## 3. HTTP to HTTPS redirect (VDOD-5)

Check the key path against the Traefik this k3s actually ships before applying:

```
kubectl -n kube-system get helmchart traefik -o yaml
kubectl apply -f deploy/vps/traefik-redirect.yaml
```

Safe to apply before any certificate exists: the ACME validator follows
redirects and does not validate the certificate it lands on.

## 4. Staging certificates (VDOD-3)

`values-prod.yaml` already names `letsencrypt-staging`. Deploy, then watch:

```
kubectl -n store get certificate
kubectl -n store describe certificate store-tls
```

Expect `READY=True` and a chain from Let's Encrypt staging, which a browser
rejects. That rejection is the expected outcome here.

## 5. Switch to production (VDOD-4)

Only once step 4 is green. One value per chart:

```
cert-manager.io/cluster-issuer: letsencrypt-prod
```

Delete the staging secrets so cert-manager reissues rather than reusing them:

```
kubectl -n store delete secret store-tls gateway-tls
```

## 6. Rotate the bootstrap key BEFORE exposing (VDOD-9)

```
scripts/rotate-gateway-key.sh store
```

The current key is in a session transcript. Rotate first, expose second.
