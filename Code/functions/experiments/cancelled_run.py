"""EXPERIMENT_ONLY：由服務建立並追蹤輸出；取消只清理本次擁有的檔案。"""
import json
from pathlib import Path
from functions.experiments.export_output import (markdown_run_paths, processed_run_paths,
                                                comment_tag_paths, chunk_run_paths)
from functions.markdown_processing.file_identity import filename_identity


class OutputSession:
    def __init__(self, settings, stage, sources, run_id):
        self.settings, self.stage, self.sources, self.run_id = settings, stage, sources, run_id
        self.batch = None
        self.active = None

    def set_output_batch(self, value):
        """核對本次階段輸出；不再由來源批次推測取消清理位置。"""
        from config.output_layout import BATCH_NAME_PATTERN
        import re
        path = Path(value).resolve()
        from functions.web_ui.catalog import STAGES
        root = getattr(self.settings, STAGES[self.stage][2]).resolve()
        if (path.parent != root or
                not re.fullmatch(BATCH_NAME_PATTERN, path.name)):
            raise ValueError('工作程序回報的輸出批次不符')
        self.batch = path

    def set_raw_batch(self, value):
        """既有呼叫相容名稱。"""
        self.set_output_batch(value)

    def begin(self, index):
        if type(index) is not int or not 0 <= index < len(self.sources):
            raise ValueError('工作程序回報的檔案序號不符')
        source = self.sources[index]
        if not self.settings.export_enabled:
            self.active = {'source':source, 'paths':{}, 'existing':set(), 'prior_record':None, 'created':{}}
            return
        if self.stage == 'raw':
            if self.batch is None:
                raise ValueError('尚未建立本次raw批次')
            paths = markdown_run_paths(self.settings.markdown_output_dir, self.batch, source.stem)
        else:
            if self.batch is None:
                raise ValueError('尚未建立本次輸出批次')
            batch = self.batch.name
            identity = filename_identity(source.name)
            if identity is None:
                raise ValueError('所選Markdown檔名缺少年度與股票代號')
            factory = {'processed': processed_run_paths, 'tagged': comment_tag_paths, 'chunk': chunk_run_paths}[self.stage]
            paths = factory(self.settings, batch, '_'.join(identity))
        paths = {k: p.resolve() for k, p in paths.items()}
        root = (self.settings.project_root/'Output').resolve()
        if not root.is_relative_to(self.settings.project_root.resolve()) or any(not p.is_relative_to(root) for p in paths.values()):
            raise ValueError('輸出位置超出本專案Output')
        prior = paths['record'].read_bytes() if paths['record'].is_file() else None
        self.active = {'source': source, 'paths': paths, 'existing': {p for p in paths.values() if p.exists()},
                       'prior_record': prior, 'created': {}}

    def create(self, value):
        if self.active is None:
            raise ValueError('沒有執行中的檔案，拒絕建立輸出')
        path = Path(value).resolve()
        plan = self.active
        record = plan['paths']['record']
        archive = path.parent == record.parent and path.name.startswith(record.name+'.failed-')
        if path not in plan['paths'].values() and not (archive and plan['prior_record'] is not None):
            raise ValueError('檔案不在本次輸出白名單')
        if path in plan['existing']:
            # 第二階段可封存同來源舊失敗報告後重試；只接受已核對的本次封存。
            backups = [p for p in plan['created'] if p.name.startswith(record.name+'.failed-')]
            if path != record or path.exists() or not backups or backups[-1].read_bytes() != plan['prior_record']:
                raise FileExistsError('不覆寫既有輸出')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            import os
            info = os.fstat(stream.fileno())
            identity = [info.st_dev, info.st_ino]
            plan['created'][path] = identity
        return identity

    def finished(self):
        self.active = None

    def cancel(self, *, reason='使用者立即取消', status='cancelled'):
        plan = self.active
        if plan is None:
            return None, []
        if not self.settings.export_enabled:
            self.active = None
            return {'name':plan['source'].name, 'status':status, 'message':'已停止；實驗寫檔未啟用'}, []
        removed, issues = [], []
        for path, identity in reversed(list(plan['created'].items())):
            try:
                if path.exists():
                    stat = path.stat()
                    if [stat.st_dev, stat.st_ino] != identity:
                        raise ValueError('檔案擁有權已改變，未刪除')
                    path.unlink()
                    removed.append(str(path))
            except (OSError, ValueError) as error:
                issues.append(f'{path.name}：{type(error).__name__}')
        record = plan['paths']['record']
        if plan['prior_record'] is not None and not record.exists():
            try:
                with record.open('xb') as stream:
                    stream.write(plan['prior_record'])
            except OSError as error:
                issues.append(f'原失敗紀錄還原失敗：{type(error).__name__}')
        report = record if not record.exists() else record.with_name(record.name+'.cancelled-'+self.run_id)
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
            with report.open('x', encoding='utf-8') as stream:
                json.dump({'schema_version':'cancelled-run/1.0', 'status':status, 'stage':self.stage,
                           'source':str(plan['source']), 'run_id':self.run_id,
                           'error':reason+'；本檔未作為成功產物，後續檔案未執行',
                           'removed_outputs':removed, 'cleanup_issues':issues,
                           'stage_timings':None, 'timing_note':'強制中止沒有完整階段計時，未填0'},
                          stream, ensure_ascii=False, indent=2)
        except OSError as error:
            issues.append(f'取消紀錄寫入失敗：{type(error).__name__}')
        result = {'name':plan['source'].name, 'status':status,
                  'message':'已立即取消，未完成產物已清理' if not issues else '已停止，輸出清理／紀錄待確認'}
        self.active = None
        return result, issues
