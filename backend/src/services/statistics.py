import math,json,hashlib
from scipy.stats import f

def anova(snapshot):
    groups=snapshot['groups']
    if len(groups)<2:raise ValueError('至少选择两种工艺方案')
    if any(len(g['samples'])<2 for g in groups):raise ValueError('每个方案至少需要2条拉力样本；不会静默移除小样本组')
    n=sum(len(g['samples']) for g in groups);k=len(groups)
    grand=sum(s['force'] for g in groups for s in g['samples'])/n
    summaries=[];between=0.;within=0.
    for g in groups:
        values=[s['force'] for s in g['samples']];mean=sum(values)/len(values)
        ss=sum((v-mean)**2 for v in values)
        between+=len(values)*(mean-grand)**2;within+=ss
        summaries.append({'id':g['id'],'code':g['code'],'name':g['name'],'n':len(values),'mean':mean,'sd':math.sqrt(ss/(len(values)-1)),'min':min(values),'max':max(values),'flagged':sum(s['flagged'] for s in g['samples'])})
    if within<=1e-12:raise ValueError('组内方差为零，F检验不成立；补充有实际测量差异的独立样本')
    df_between=k-1;df_within=n-k
    ms_between=between/df_between;ms_within=within/df_within
    statistic=ms_between/ms_within;p=float(f.sf(statistic,df_between,df_within))
    return {'mode':'strip','n':n,'groups':summaries,'grand_mean':grand,'ss_between':between,'ss_within':within,'ss_total':between+within,'df_between':df_between,'df_within':df_within,'ms_between':ms_between,'ms_within':ms_within,'f':statistic,'p':p,'eta_squared':between/(between+within),'significant':p<.05,'flagged':sum(g['flagged'] for g in summaries),'checksum':hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'method':'单因素独立样本 ANOVA；α=0.05；异常标记样本全部保留；要求独立、组内近似正态与方差齐性。显著F不说明哪一组更优，也不替代工艺合格判定。'}

def merge_stats(parts):
    # Chan et al. 并行合并：输入 (n, mean, m2)，m2 为组内离均差平方和；数值稳定，不展开逐条测量
    n=0;mean=0.;m2=0.
    for pn,pmean,pm2 in parts:
        if pn<=0:continue
        if n==0:n,mean,m2=pn,pmean,pm2;continue
        total=n+pn;delta=pmean-mean
        mean+=delta*pn/total;m2+=pm2+delta*delta*n*pn/total;n=total
    return n,mean,m2

def anova_summary(snapshot):
    groups=snapshot['groups']
    if len(groups)<2:raise ValueError('至少选择两种工艺方案')
    missing=[]
    for g in groups:
        if not g['expected']:missing.append(f"{g['code']} 未登记预期编号范围")
        elif g['gaps']:missing.append(f"{g['code']} 缺包 "+"、".join(f"{x['start_no']}–{x['end_no']}" for x in g['gaps']))
    if missing:raise ValueError('缺包未收全，不给结论：'+'；'.join(missing)+'。请在汇总收包页核查缺口、收齐后重新发起。')
    merged=[]
    for g in groups:
        if not g['packages']:raise ValueError(f"{g['code']} 没有已接收的汇总包")
        n,mean,m2=merge_stats([(p['n'],p['mean'],(p['n']-1)*p['sd']**2) for p in g['packages']])
        if n<2:raise ValueError(f"{g['code']} 合并后样本不足2条")
        merged.append((g,n,mean,m2))
    n=sum(x[1] for x in merged);k=len(merged)
    grand=sum(x[1]*x[2] for x in merged)/n
    summaries=[];between=0.;within=0.
    for g,gn,gmean,m2 in merged:
        between+=gn*(gmean-grand)**2;within+=m2
        summaries.append({'id':g['id'],'code':g['code'],'name':g['name'],'n':gn,'mean':gmean,'sd':math.sqrt(m2/(gn-1)),'min':None,'max':None,'flagged':None,'packages':len(g['packages'])})
    if within<=1e-12:raise ValueError('组内方差为零，F检验不成立；补充有实际测量差异的独立样本')
    df_between=k-1;df_within=n-k
    ms_between=between/df_between;ms_within=within/df_within
    statistic=ms_between/ms_within;p=float(f.sf(statistic,df_between,df_within))
    return {'mode':'summary','n':n,'groups':summaries,'grand_mean':grand,'ss_between':between,'ss_within':within,'ss_total':between+within,'df_between':df_between,'df_within':df_within,'ms_between':ms_between,'ms_within':ms_within,'f':statistic,'p':p,'eta_squared':between/(between+within),'significant':p<.05,'flagged':None,'checksum':hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'method':'单因素独立样本 ANOVA（外协汇总包合并：以各包 n、均值、样本标准差按 Chan 并行算法精确合并，不展开虚构逐条测量；与逐条计算在浮点精度内一致）；α=0.05；汇总包不含逐条最小/最大与异常标记；要求独立、组内近似正态与方差齐性。显著F不说明哪一组更优，也不替代工艺合格判定。'}
