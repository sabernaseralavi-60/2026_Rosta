import type { Metadata } from 'next';

import { CertificatesAdminView } from './CertificatesAdminView';

export const metadata: Metadata = {
  title: 'گواهی‌ها',
  description: 'جستجوی گواهی با کد و ابطال با دلیل.',
};

/** `/admin/certificates` — FR-PRJ-08، ADR-0017. */
export default function CertificatesAdminPage() {
  return <CertificatesAdminView />;
}
