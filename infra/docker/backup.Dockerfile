# SILP — کانتینر پشتیبان‌گیری — M7-17
#
# چرا نه ایمیج API (آن‌طور که §12.5 نوشته بود): postgresql-client دبیان
# bookworm نسخهٔ ۱۵ است و pg_dump ۱۵ از سرور ۱۶ پشتیبان نمی‌گیرد
# («server version mismatch»). پشتیبان باید با ابزار هم‌نسخهٔ سرور گرفته
# شود؛ همان ایمیج postgres:16 این را تضمین می‌کند.
FROM postgres:16-alpine

RUN apk add --no-cache bash aws-cli findutils coreutils tzdata

ENV TZ=Asia/Tehran \
    BACKUP_DIR=/backups

COPY infra/scripts/backup.sh infra/scripts/basebackup.sh infra/scripts/backup-loop.sh \
     infra/scripts/restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh

USER postgres
ENTRYPOINT []
CMD ["/usr/local/bin/backup-loop.sh"]
