"""Compare manually sampled answers using the same question and platform entry."""
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from django.utils import timezone

GROUP_FIELDS = ('trial', 'brand', 'platform', 'surface', 'intent', 'cohort', 'question')
SAMPLE_FIELDS = (
    'phase', 'observed_at', 'outcome', 'mentioned', 'recommended',
    'citation_status', 'own_cited', 'owned_site', 'citations',
)


def hostname(value):
    host = (urlsplit(value).hostname or '').lower().rstrip('.')
    return host.removeprefix('www.')


def is_owned(host, domain):
    return bool(domain) and (host == domain or host.endswith('.' + domain))


def _empty_phase():
    return {
        'valid': 0, 'mentioned': 0, 'recommended': 0, 'citation_samples': 0, 'own_cited': 0,
        'dates': set(), 'recommendation_dates': set(), 'citation_sample_dates': set(),
        'citation_dates': set(), 'domains': set(),
    }


def _record_sample(phase, sample):
    observed_at = datetime.fromisoformat(sample['observed_at'])
    date = (timezone.localtime(observed_at) if timezone.is_aware(observed_at) else observed_at).date()
    phase['valid'] += 1
    phase['dates'].add(date)
    phase['mentioned'] += int(sample['mentioned'])
    if sample['recommended']:
        phase['recommended'] += 1
        phase['recommendation_dates'].add(date)
    if sample['citation_status'] != 'unknown':
        phase['citation_samples'] += 1
        phase['citation_sample_dates'].add(date)
        phase['domains'].add(sample['owned_site'])
    if sample['own_cited']:
        phase['own_cited'] += 1
        phase['citation_dates'].add(date)


def _phase_payload(phase):
    fields = ('valid', 'mentioned', 'recommended', 'citation_samples', 'own_cited')
    return {**{field: phase[field] for field in fields}, 'dates': len(phase['dates'])}


def _new_signals(before, after):
    if (min(before['valid'], after['valid']) < 3 or min(len(before['dates']), len(after['dates'])) < 2
            or max(before['dates']) >= min(after['dates'])):
        return []
    signals = []
    if before['recommended'] == 0 and len(after['recommendation_dates']) >= 2:
        signals.append('recommendation')
    if (before['domains'] == after['domains'] and len(before['domains']) == 1
            and min(before['citation_samples'], after['citation_samples']) >= 3
            and len(before['citation_sample_dates']) >= 2
            and before['own_cited'] == 0 and len(after['citation_dates']) >= 2):
        signals.append('citation')
    return signals


def matched_questions(records):
    fields = GROUP_FIELDS + SAMPLE_FIELDS
    groups = {}
    rows = records.order_by().values_list(*(f'data__{field}' for field in fields)).iterator()
    for values in rows:
        sample = dict(zip(fields, values))
        if sample['outcome'] != 'answer':
            continue
        key = tuple(sample[field] or '' for field in GROUP_FIELDS)
        if key not in groups:
            groups[key] = {'baseline': _empty_phase(), 'retest': _empty_phase(), 'sources': Counter()}
        group = groups[key]
        _record_sample(group[sample['phase']], sample)
        if sample['phase'] == 'baseline' and sample['intent'] == 'category' and not sample['mentioned']:
            group['sources'].update({
                url for url in sample['citations'] if not is_owned(hostname(url), sample['owned_site'])
            })

    report = []
    for key, group in sorted(groups.items()):
        row = dict(zip(GROUP_FIELDS, key))
        before, after = group['baseline'], group['retest']
        row.update(baseline=_phase_payload(before), retest=_phase_payload(after))
        row['sources'] = [{'url': url, 'answers': count} for url, count in
                          sorted(group['sources'].items(), key=lambda item: (-item[1], item[0]))[:3]]
        row['signals'] = (
            _new_signals(before, after) if row['intent'] == 'category' and row['trial'] and row['cohort'] else []
        )
        report.append(row)
    return report
