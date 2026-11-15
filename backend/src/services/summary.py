from datetime import datetime,timezone
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import ExpectedRange,SummaryPackage,Process
from src.services.statistics import merge_stats

def _now():return datetime.now(timezone.utc).isoformat()
def _lock_group(db,process_id,lot):
    # 同一（工艺,批次）的收包/登记串行化：交叠检查与插入在同一事务内，杜绝并发交叠争抢
    if db.get_bind().dialect.name=='postgresql':
        db.execute(text('select pg_advisory_xact_lock(hashtext(:k))'),{'k':f'summary:{process_id}:{lot}'})
def _process(db,process_id):
    process=db.get(Process,process_id)
    if not process:raise HTTPException(404,'工艺方案不存在')
    return process

def list_expectations(db,process_id=None,lot=None):
    q=select(ExpectedRange).order_by(ExpectedRange.process_id,ExpectedRange.lot,ExpectedRange.start_no)
    if process_id:q=q.where(ExpectedRange.process_id==process_id)
    if lot:q=q.where(ExpectedRange.lot==lot)
    return db.scalars(q).all()
def create_expectation(db,data,user):
    _process(db,data.process_id)
    _lock_group(db,data.process_id,data.lot)
    exact=db.scalar(select(ExpectedRange).where(ExpectedRange.process_id==data.process_id,ExpectedRange.lot==data.lot,ExpectedRange.start_no==data.start_no,ExpectedRange.end_no==data.end_no))
    if exact:return exact,False
    overlap=db.scalars(select(ExpectedRange).where(ExpectedRange.process_id==data.process_id,ExpectedRange.lot==data.lot,ExpectedRange.start_no<=data.end_no,ExpectedRange.end_no>=data.start_no).order_by(ExpectedRange.start_no)).all()
    if overlap:
        o=overlap[0];raise HTTPException(409,f'预期范围 {data.start_no}–{data.end_no} 与已登记范围 {o.start_no}–{o.end_no} 交叠，本次登记整段拒收')
    item=ExpectedRange(process_id=data.process_id,lot=data.lot,start_no=data.start_no,end_no=data.end_no,note=data.note,created_by=user.email,created_at=_now())
    db.add(item)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        again=db.scalar(select(ExpectedRange).where(ExpectedRange.process_id==data.process_id,ExpectedRange.lot==data.lot,ExpectedRange.start_no==data.start_no,ExpectedRange.end_no==data.end_no))
        if again:return again,False
        raise HTTPException(409,'预期范围与并发登记交叠，本次登记整段拒收')
    db.refresh(item);return item,True

def list_packages(db,process_id=None,lot=None):
    q=select(SummaryPackage).order_by(SummaryPackage.process_id,SummaryPackage.lot,SummaryPackage.start_no)
    if process_id:q=q.where(SummaryPackage.process_id==process_id)
    if lot:q=q.where(SummaryPackage.lot==lot)
    return db.scalars(q).all()
def _same_content(item,data):
    return (item.process_id==data.process_id and item.lot==data.lot and item.start_no==data.start_no and item.end_no==data.end_no
            and item.n==data.n and item.mean==data.mean and item.sd==data.sd)
def receive_package(db,data,user):
    _process(db,data.process_id)
    _lock_group(db,data.process_id,data.lot)
    same_no=db.scalar(select(SummaryPackage).where(SummaryPackage.package_no==data.package_no))
    if same_no:
        if _same_content(same_no,data):return same_no,False
        raise HTTPException(409,f'包号 {data.package_no} 已接收但统计内容不一致，同号异内容整包拒收；请与外协核对后换新包号')
    overlap=db.scalars(select(SummaryPackage).where(SummaryPackage.process_id==data.process_id,SummaryPackage.lot==data.lot,SummaryPackage.start_no<=data.end_no,SummaryPackage.end_no>=data.start_no).order_by(SummaryPackage.start_no)).all()
    if overlap:
        o=overlap[0];raise HTTPException(409,f'编号范围 {data.start_no}–{data.end_no} 与已收包 {o.package_no}（{o.start_no}–{o.end_no}）交叠，整包拒收')
    item=SummaryPackage(package_no=data.package_no,process_id=data.process_id,lot=data.lot,start_no=data.start_no,end_no=data.end_no,n=data.n,mean=data.mean,sd=data.sd,note=data.note,received_by=user.email,created_at=_now())
    db.add(item)
    try:db.commit()
    except IntegrityError:
        # 并发下同包号唯一约束兜底：内容一致按重试处理，不一致整包拒收
        db.rollback()
        again=db.scalar(select(SummaryPackage).where(SummaryPackage.package_no==data.package_no))
        if again and _same_content(again,data):return again,False
        raise HTTPException(409,f'包号 {data.package_no} 已接收但统计内容不一致，同号异内容整包拒收；请与外协核对后换新包号')
    db.refresh(item);return item,True

def _subtract(intervals,cut_start,cut_end):
    out=[]
    for a,b in intervals:
        if cut_end<a or cut_start>b:out.append((a,b));continue
        if a<cut_start:out.append((a,cut_start-1))
        if cut_end<b:out.append((cut_end+1,b))
    return out
def coverage(db,process_id,lot):
    process=_process(db,process_id)
    expectations=db.scalars(select(ExpectedRange).where(ExpectedRange.process_id==process_id,ExpectedRange.lot==lot).order_by(ExpectedRange.start_no)).all()
    packages=db.scalars(select(SummaryPackage).where(SummaryPackage.process_id==process_id,SummaryPackage.lot==lot).order_by(SummaryPackage.start_no)).all()
    expected=[];gaps=[]
    for e in expectations:
        uncovered=[(e.start_no,e.end_no)]
        for p in packages:uncovered=_subtract(uncovered,p.start_no,p.end_no)
        count=e.end_no-e.start_no+1;missing_count=sum(b-a+1 for a,b in uncovered)
        expected.append({'id':e.id,'start_no':e.start_no,'end_no':e.end_no,'count':count,'received':count-missing_count,'missing':[{'start_no':a,'end_no':b,'count':b-a+1} for a,b in uncovered],'status':'已收全' if not uncovered else('未收' if missing_count==count else '部分缺口')})
        gaps+=[{'start_no':a,'end_no':b,'count':b-a+1} for a,b in uncovered]
    outside=[p for p in packages if not any(p.start_no>=e.start_no and p.end_no<=e.end_no for e in expectations)]
    n,mean,m2=merge_stats([(p.n,p.mean,(p.n-1)*p.sd**2) for p in packages])
    merged={'n':n,'mean':mean if n else None,'sd':(m2/(n-1))**.5 if n>=2 else None,'packages':len(packages)}
    return {'process_id':process_id,'process_code':process.code,'lot':lot,'expected':expected,'gaps':gaps,'complete':bool(expectations) and not gaps,'outside_packages':[p.package_no for p in outside],'merged':merged,'packages':[{'id':p.id,'package_no':p.package_no,'start_no':p.start_no,'end_no':p.end_no,'n':p.n,'mean':p.mean,'sd':p.sd,'received_by':p.received_by,'created_at':p.created_at} for p in packages]}
