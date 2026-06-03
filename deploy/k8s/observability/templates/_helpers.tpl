{{/* Common helpers for the InvForge observability chart. */}}

{{- define "obs.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- range $k, $v := .Values.commonLabels }}
{{ $k }}: {{ $v | quote }}
{{- end }}
{{- end -}}

{{/* AI API in-cluster FQDN target for Prometheus scraping. */}}
{{- define "obs.aiApiTarget" -}}
{{ .Values.aiApi.service }}.{{ .Values.aiApi.namespace }}.svc.cluster.local:{{ .Values.aiApi.port }}
{{- end -}}
