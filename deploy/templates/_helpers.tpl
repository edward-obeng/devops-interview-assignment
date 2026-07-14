{{/*
Resource name prefix — parameterized by realm, not the release name, so the
naming convention stays predictable across realms (one release per realm).
*/}}
{{- define "keycloak-stale-cleanup.fullname" -}}
{{ .Values.realm }}-cleanup
{{- end -}}

{{- define "keycloak-stale-cleanup.labels" -}}
app.kubernetes.io/name: keycloak-stale-cleanup
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
realm: {{ .Values.realm }}
{{- end -}}

{{- define "keycloak-stale-cleanup.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "keycloak-stale-cleanup.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Secret to read the Keycloak client secret from — an existing one if given,
otherwise the one this chart creates from values.keycloak.clientSecret.
*/}}
{{- define "keycloak-stale-cleanup.secretName" -}}
{{- if .Values.keycloak.existingSecret -}}
{{ .Values.keycloak.existingSecret }}
{{- else -}}
{{ include "keycloak-stale-cleanup.fullname" . }}-secret
{{- end -}}
{{- end -}}
