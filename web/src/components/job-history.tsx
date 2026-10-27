import { Fragment, useState } from 'react';
import { Clock, LoaderCircle, CircleCheck, CircleX, CircleSlash, CircleHelp } from 'lucide-react';
import { t, tr, locale } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible';
import { Button } from './ui/button';
import { PageControls } from './page-controls';
import { imageSeedLabel } from '../controllers/backend-controls.mjs';

const statuses: Record<string, string> = { queued: '等待生成', submitting: '正在提交', running: '正在生成', completed: '已完成', failed: '生成失败', cancelled: '已取消', unknown: '状态待确认' };
const icons: Record<string, any> = { queued: Clock, submitting: LoaderCircle, running: LoaderCircle, completed: CircleCheck, failed: CircleX, cancelled: CircleSlash };
function JobCard({ job, busy, cancel, open, setOpen }: { job: any; busy: boolean; cancel: () => void; open: boolean; setOpen: (open: boolean) => void }) {
  const Icon = icons[job.status] || CircleHelp;
  const label = t(statuses[job.status] || job.status);
  const date = new Date(job.created_at).toLocaleString(locale(), { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  const fullDate = new Date(job.created_at).toLocaleString(locale());
  return <Collapsible className="job" data-job-id={job.id} open={open} onOpenChange={setOpen}>
    <CollapsibleTrigger asChild><Button variant="ghost" className="collapsible-label" data-tooltip={t('展开或收起任务详情')} aria-label={tr`${label} · ${job.id} · ${date} · 任务详情`}>
      <span className={`job-status job-status-${job.status}`} role="img" aria-label={label} data-tooltip={label}><Icon /></span><span className="job-identifier" data-tooltip={tr`任务 ID：${job.id}`}>{job.id}</span><span className="job-time" role="img" aria-label={fullDate} data-tooltip={fullDate}><Clock /></span>
    </Button></CollapsibleTrigger>
    <CollapsibleContent hidden={!open}><div className="job-body"><dl className="job-meta">{[[t('状态'), label], [t('时间'), fullDate], [t('生图 API'), job.backend_name || job.backend_id], [t('种子'), imageSeedLabel(job)], ...(job.width && job.height ? [[t('请求尺寸'), `${job.width}×${job.height}`]] : []), [t('任务 ID'), job.id]].map(([key, value]) => <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>)}</dl>
      {[[t('正向提示词'), job.positive], [t('负向提示词'), job.negative]].map(([key, value]) => value && <Fragment key={key}><h3>{key}</h3><p className="job-prompt">{value}</p></Fragment>)}
      {job.error && <p className="job-error">{job.error}</p>}
      {['queued', 'submitting', 'running'].includes(job.status) && <div className="job-actions"><Button disabled={busy} onClick={cancel}>{t('取消任务')}</Button></div>}
    </div></CollapsibleContent>
  </Collapsible>;
}
export function JobHistory() {
  const app = useApplication(), state = useModel(app.model);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const page = state.jobPage || { items: [], page: 1, totalPages: 1, loading: false, loaded: false, total: 0 };
  return <section id="jobs-view" aria-label={t('任务记录')}><h2 className="mb-4">{t('任务记录')}</h2>
    {page.loaded && !page.total && !page.loading && !page.error && <div id="jobs-empty" className="empty small"><h2>{t('还没有生成任务')}</h2></div>}
    <div id="job-list" className="job-list" inert={page.loading} aria-busy={page.loading}>{page.items.map((job: any) => <JobCard key={job.id} job={job} open={expanded.has(job.id)} setOpen={open => setExpanded(previous => { const next = new Set(previous); if (open) next.add(job.id); else next.delete(job.id); return next; })} busy={state.cancellingJobs.includes(job.id)} cancel={() => app.cancelJob(job.id)} />)}</div>
    {page.loading && <p className="hint" role="status">{t('正在读取任务…')}</p>}
    {(page.loading || page.error || page.total > 0) && <PageControls label={t('任务')} {...page} onPageChange={number => app.jobPager.load(number)} />}
  </section>;
}
