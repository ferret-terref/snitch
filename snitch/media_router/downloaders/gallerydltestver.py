from gallery_dl import job as gallery_job


class DebugJob(gallery_job.DownloadJob):
    def dispatch(self, msg):
        print(msg)  # inspect everything gallery-dl emits
        return super().dispatch(msg)


job = DebugJob("https://www.pixiv.net/en/artworks/123456789")
job.run()