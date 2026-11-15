/** @typedef {{id:number,code:string,name:string,temperature:number,dwell:number,pressure:number,note:string}} Process */
/** @typedef {{id:number,code:string,process_id:number,lot:string,force:number,flagged:boolean,note:string}} Sample */
/** @typedef {{id:number,title:string,status:'queued'|'running'|'completed'|'failed',snapshot:object,result:object|null,recommendation:string,approved:boolean}} Assessment */
/** @typedef {{id:number,process_id:number,lot:string,start_no:number,end_no:number,note:string,created_by:string,created_at:string}} ExpectedRange */
/** @typedef {{id:number,package_no:string,process_id:number,lot:string,start_no:number,end_no:number,n:number,mean:number,sd:number,note:string,received_by:string,created_at:string,deduplicated?:boolean}} SummaryPackage */
/** @typedef {{process_id:number,process_code:string,lot:string,expected:Array<{id:number,start_no:number,end_no:number,count:number,received:number,missing:Array<{start_no:number,end_no:number,count:number}>,status:string}>,gaps:Array<{start_no:number,end_no:number,count:number}>,complete:boolean,outside_packages:string[],merged:{n:number,mean:number|null,sd:number|null,packages:number},packages:SummaryPackage[]}} GapReport */
export const contractsVersion='seal-variance-2';
