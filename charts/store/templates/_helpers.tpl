{{- define "store.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "store.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "store.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "store.labels" -}}
app.kubernetes.io/name: {{ include "store.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "store.db.fullname" -}}
{{- printf "%s-db" (include "store.fullname" .) -}}
{{- end -}}

{{- define "store.wp.fullname" -}}
{{- printf "%s-wp" (include "store.fullname" .) -}}
{{- end -}}

{{/*
Guard: the chart refuses to render without an explicit ingress class and host.
Leaving these empty is how a chart silently depends on whatever the cluster
defaults to, which is exactly what D-002 forbids.
*/}}
{{- define "store.require" -}}
{{- if .Values.ingress.enabled -}}
{{- if not .Values.ingress.className -}}
{{- fail "ingress.className is required. Set it in values-local.yaml or values-prod.yaml." -}}
{{- end -}}
{{- if not .Values.ingress.host -}}
{{- fail "ingress.host is required. Set it in values-local.yaml or values-prod.yaml." -}}
{{- end -}}
{{- end -}}
{{- end -}}
