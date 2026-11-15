from fastapi import APIRouter,Depends,Response
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import ExpectedRangeInput,SummaryPackageInput
from src.services import summary
from src.controllers.business import serialize,serialize_many
router=APIRouter()
@router.get('/summary/expectations')
def expectations(process_id:int|None=None,lot:str|None=None,db=Depends(get_db),user=Depends(current_user)):return serialize_many(summary.list_expectations(db,process_id,lot))
@router.post('/summary/expectations')
def create_expectation(data:ExpectedRangeInput,response:Response,db=Depends(get_db),user=Depends(editor)):
    item,created=summary.create_expectation(db,data,user)
    response.status_code=201 if created else 200
    return {**serialize(item),'deduplicated':not created}
@router.get('/summary/packages')
def packages(process_id:int|None=None,lot:str|None=None,db=Depends(get_db),user=Depends(current_user)):return serialize_many(summary.list_packages(db,process_id,lot))
@router.post('/summary/packages')
def receive(data:SummaryPackageInput,response:Response,db=Depends(get_db),user=Depends(editor)):
    item,created=summary.receive_package(db,data,user)
    response.status_code=201 if created else 200
    return {**serialize(item),'deduplicated':not created}
@router.get('/summary/gaps')
def gaps(process_id:int,lot:str,db=Depends(get_db),user=Depends(current_user)):return summary.coverage(db,process_id,lot)
