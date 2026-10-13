{{- define "geostudio.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}{{ .Release.Name | trunc 50 | trimSuffix "-" }}{{- else -}}{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 50 | trimSuffix "-" }}{{- end -}}
{{- end -}}

{{- define "geostudio.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "geostudio.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* image : <registry>/geostudio-<name>:<tag> ; tag = .Values.image.tag, sinon appVersion */}}
{{- define "geostudio.image" -}}
{{ .root.Values.image.registry }}/geostudio-{{ .name }}:{{ .root.Values.image.tag | default .root.Chart.AppVersion }}
{{- end -}}

{{/* secretKeyRef pour une liste de noms ; les clés du Secret portent le nom de la variable d'env.
     Entrée : dict "root" . "names" (liste) "optional" bool. */}}
{{- define "geostudio.secretEnv" -}}
{{- range .names }}
- name: {{ . }}
  valueFrom:
    secretKeyRef:
      name: {{ required "secrets.existingSecret est obligatoire (aucun secret en clair dans values)" $.root.Values.secrets.existingSecret }}
      key: {{ . }}
      optional: {{ $.optional }}
{{- end }}
{{- end -}}

{{- define "geostudio.securityContext" -}}
runAsNonRoot: true
runAsUser: {{ .uid }}
runAsGroup: {{ .uid }}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
