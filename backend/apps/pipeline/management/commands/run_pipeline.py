from django.core.management.base import BaseCommand

from apps.pipeline.worker import PipelineError, execute_task, queued_tasks


class Command(BaseCommand):
    help = 'Run queued AI writing tasks.'

    def handle(self, *args, **options):
        ran = 0
        failed = 0
        for task in queued_tasks():
            try:
                result = execute_task(task.id)
            except PipelineError as exc:
                failed += 1
                self.stderr.write(f'task {task.id} failed: {exc}')
                continue
            ran += 1
            self.stdout.write(
                f'task {task.id} {result.get("pipeline_status")} articles={result.get("success_count")}'
            )
        self.stdout.write(self.style.SUCCESS(f'pipeline finished ran={ran} failed={failed}'))
