# Elevation probe uses invariant BUILTIN\Administrators SID (S-1-5-32-544).
# Do not pass localized group display names to IsInRole.
function Test-WorkspaceAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
