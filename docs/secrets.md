# sealed-secrets

> *Note*: this document is a work in progress

## Fetch Sealed Secrets Cert

```bash
kubeseal --kubeconfig ./kubeconfig --controller-name sealed-secrets --fetch-cert > ./secrets/pub-cert.pem
```

```bash
kubectl --kubeconfig ./kubeconfig apply -f ./cluster/zz_generated_secrets.yaml 
```