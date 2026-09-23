/** کدی که هرگز صادر نشده — §3.8 «پیام قابل فهم + قدم بعدی». */
export default function CertificateNotFound() {
  return (
    <div className="page">
      <div className="mx-auto flex max-w-[640px] flex-col gap-4 py-16 text-center">
        <h1>گواهی با این کد پیدا نشد</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          کد را با آنچه روی گواهی نوشته شده مقایسه کن — هشت نویسه، مثل{' '}
          <span className="font-mono" dir="ltr">
            7KQ2-MX9P
          </span>
          . حروف کوچک و بزرگ و خط تیره فرقی ندارند؛ اگر باز هم پیدا نشد، این گواهی از سامانهٔ ما
          صادر نشده است.
        </p>
      </div>
    </div>
  );
}
