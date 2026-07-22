/** Map SQL link_status to design-system tone classes (presentation only). */
export function linkToneClass(status: string | null | undefined): string {
  switch (status) {
    case 'ok':
      return 'tone-success'
    case 'partial':
    case 'fallback_full':
      return 'tone-warning'
    case 'failed':
      return 'tone-danger'
    default:
      return 'tone-muted'
  }
}
