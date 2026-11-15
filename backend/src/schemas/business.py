from typing import Literal
from pydantic import BaseModel,Field,model_validator
class LoginInput(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=200)
class ProcessInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    name:str=Field(min_length=2,max_length=100)
    temperature:float=Field(ge=80,le=250,allow_inf_nan=False)
    dwell:float=Field(gt=0,le=10,allow_inf_nan=False)
    pressure:float=Field(gt=0,le=2,allow_inf_nan=False)
    note:str=Field(default='',max_length=2000)
class SampleInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    process_id:int=Field(gt=0)
    lot:str=Field(min_length=1,max_length=60)
    force:float=Field(gt=0,le=200,allow_inf_nan=False)
    flagged:bool=False
    note:str=Field(default='',max_length=1000)
class AssessmentInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    process_ids:list[int]=Field(min_length=2,max_length=8)
    lot:str=Field(default='全部',min_length=1,max_length=60)
    mode:Literal['strip','summary']='strip'
class RecommendationInput(BaseModel):
    selected_process_id:int=Field(gt=0)
    recommendation:str=Field(min_length=20,max_length=3000)
class ExpectedRangeInput(BaseModel):
    process_id:int=Field(gt=0)
    lot:str=Field(min_length=1,max_length=60)
    start_no:int=Field(ge=1,le=1_000_000_000)
    end_no:int=Field(ge=1,le=1_000_000_000)
    note:str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def ordered(self):
        if self.end_no<self.start_no:raise ValueError('预期范围终点不能小于起点')
        return self
class SummaryPackageInput(BaseModel):
    package_no:str=Field(min_length=1,max_length=50)
    process_id:int=Field(gt=0)
    lot:str=Field(min_length=1,max_length=60)
    start_no:int=Field(ge=1,le=1_000_000_000)
    end_no:int=Field(ge=1,le=1_000_000_000)
    n:int=Field(ge=2,le=100_000_000)
    mean:float=Field(gt=0,le=200,allow_inf_nan=False)
    sd:float=Field(ge=0,le=200,allow_inf_nan=False)
    note:str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def consistent(self):
        if self.end_no<self.start_no:raise ValueError('编号范围终点不能小于起点')
        if self.n!=self.end_no-self.start_no+1:raise ValueError('数量 n 须等于连续编号范围长度（end_no−start_no+1）')
        return self
