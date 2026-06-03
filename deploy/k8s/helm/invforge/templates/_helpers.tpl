{{/*
Common helpers for the InvForge chart.
*/}}

{{- define "invforge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "invforge.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels applied to every resource.
*/}}
{{- define "invforge.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- range $k, $v := .Values.commonLabels }}
{{ $k }}: {{ $v | quote }}
{{- end }}
{{- end -}}

{{/*
AI API selector labels.
*/}}
{{- define "invforge.aiApi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "invforge.name" . }}
app.kubernetes.io/component: ai-api
{{- end -}}

{{/*
BentoML selector labels (component only; color/version added per-deployment).
*/}}
{{- define "invforge.bentoml.selectorLabels" -}}
app.kubernetes.io/name: {{ include "invforge.name" . }}
app.kubernetes.io/component: bentoml
{{- end -}}

{{/*
The AI layer namespace.
*/}}
{{- define "invforge.namespace" -}}
{{- .Values.namespaces.ai -}}
{{- end -}}
