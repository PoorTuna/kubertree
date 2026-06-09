# Helm deployment

Chart: `helm/kubertree`. Values are validated against `values.schema.json`.

## Values

| Key | Default | Purpose |
|---|---|---|
| `image.repository` | `docker.io/poortuna/kubertree` | Image (Docker Hub) |
| `image.tag` | `0.2.0` | Image tag |
| `imagePullSecrets` | `[]` | Pull secret(s) for a private repo |
| `oauthProxy.enabled` | `false` | OpenShift SSO sidecar |
| `oauthProxy.image` | `quay.io/openshift/origin-oauth-proxy:4.14` | Proxy image |
| `service.type` / `service.port` | `ClusterIP` / `80` | Service |
| `ingress.enabled` / `ingress.host` | `false` | Ingress (token-paste auth) |
| `route.enabled` / `route.host` | `false` | OpenShift Route |
| `resources` | 50m/96Mi → 250m/256Mi | Requests/limits |

## OpenShift (SSO)

```bash
helm install kubertree ./helm/kubertree -n kubertree --create-namespace \
  --set image.tag=0.2.0 \
  --set oauthProxy.enabled=true \
  --set route.enabled=true
```

The sidecar terminates TLS with an OpenShift service-serving certificate and
forwards each user's token; the Route is set to reencrypt automatically. The
ServiceAccount is bound only to `system:auth-delegator` so the proxy can run
TokenReview/SubjectAccessReview — no resource permissions are granted to the app.

## Vanilla Kubernetes (token-paste)

```bash
helm install kubertree ./helm/kubertree -n kubertree --create-namespace \
  --set image.tag=0.2.0 \
  --set ingress.enabled=true --set ingress.host=kubertree.example.com
```

Terminate TLS at the ingress: the session cookie carries a bearer token. Users
sign in once with `kubectl create token <serviceaccount>` or their own token.

## RBAC

The chart creates no ClusterRole for the app. Actions run as the signed-in user,
so their existing roles apply. The only optional binding is to the built-in
`system:auth-delegator`, created when `oauthProxy.enabled=true`.
