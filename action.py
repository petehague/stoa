#!/usr/bin/env python

import cwltool.factory
from cwltool.factory import WorkflowStatus
from yml import yamler, writeyaml
import re
import os
import sys
import shutil
import time
import glob
import tempfile
from cwltool.errors import WorkflowException

from worktable import Worktable

from concurrent import futures
import grpc
import action_pb2
import action_pb2_grpc

import userstate_interface as userstate

targetFolder = sys.argv[1]

scriptPath = os.path.realpath(__file__)
coreFolder = os.path.split(scriptPath)[0]
scriptFolder = os.path.join(coreFolder,"actions")

os.environ['PATH'] += ":"+scriptFolder

lockQueue = 0 

procQueue = {}
procCheck = {}

def ymlvars(ymlfile, output, pathname):
    f1 = open(ymlfile,"r")
    f2 = open(output,"w")
    for line in f1:
        result = line.replace("<path>", pathname)
        f2.write(result)
    f1.close()
    f2.close()

def cwlinvoke(pathname, taskfile, params, userPath):
    oldpath = os.environ["PATH"]
    os.environ["PATH"] += ":" + userPath

    taskfac = cwltool.factory.Factory()
    t = taskfac.make(os.path.join(pathname,taskfile))
    params["preserve-environment"]="PATH"
    params["basedir"]=pathname
    #params["preserve-entire-environment"]="0"
    result = t(**params)

    os.environ["PATH"] = oldpath
    return result

def parsecwloutput(pathname, result, fields, l=False):
    outlist = []
    for fieldname in fields:
       if fieldname in result:
            outobj = result[fieldname]
            if type(outobj) is dict:           
                if outobj['basename']=='list.txt':
                    f = open(outobj['location'][7:], "r")
                    data = []
                    for line in f:
                        data.append(line.strip())
                    f.close()
                    data = ['-'] if data==[] else data
                    outlist.append(data)
                    continue
                if outobj['class']=='File':
                    outlist.append(os.path.join(pathname,outobj['basename']))
                    shutil.copyfile(outobj['location'][7:], 
                                    os.path.join(pathname, outobj['basename']))
            else:
                if type(outobj) is list:
                    oldoutobj = outobj
                    outobj = []
                    for item in oldoutobj:
                        if type(item) is dict:
                            if item['class']=='File':
                                outobj.append(os.path.join(pathname,item['basename']))
                                shutil.copyfile(item['location'][7:], 
                                                os.path.join(pathname, item['basename']))
                        else:
                            outobj.append(item)
                outlist.append(outobj)
    return outlist

def ExecCWL(cmdFile, pathname, bindex):
    result = {}
    success = 0

    wt = Worktable(cmdFile)
    userPath = os.path.split(cmdFile)[0]
    wtFile = cmdFile
    cmdFile = "workflow.cwl"
    wt.unpack(pathname)
    cmdDict = {}
    for i in range(len(wt.fieldnames)):
        if "I_" in wt.fieldtypes[i]:
            contents = wt[wt.bybindex(bindex)][i]
            if "file" in wt.fieldtypes[i]:
                cmdDict[wt.fieldnames[i]] = {"class": "File", "location": "file://"+contents}
            else:
                cmdDict[wt.fieldnames[i]] = contents
    cmdDict["STOA_targetfolder"] = targetFolder

    try:
        result = cwlinvoke(pathname, cmdFile, cmdDict, userPath)
        #writeyaml(result, pathname+"/.pipelog.txt")
    except WorkflowException as werr:
        success = 1
        log = open(pathname+"/.pipelog.txt","a")
        log.write("Workflow Exception: {}\n".format(werr.args))
        log.close()
        print("Workflow Exception: {}\n".format(werr.args))
        wt = False
    except WorkflowStatus as wstat:
        print("Workflow failed with status: {}\n".format(wstat.args))
        wt = False
    except Exception as e:
        print("Exception during action: {}\n".format(e.args))
        wt = False
    if wt:
        wt.update(wt.bybindex(bindex),parsecwloutput(pathname, result, wt.fieldnames))
        wt.save(wtFile)
                
    return success

def makeyml(pathname, command, bindex):
    """
    Generates a yml file to guide execution

    :param pathname: The path of the project of interest
    """

    if ".wtx" in command:
        wt = Worktable(command)
        cmdDict = wt.template
    else:
        cmdyml = (re.split(".cwl", command)[0]).strip() + ".yml"
        cmdDict = yamler(open(scriptFolder+"/"+cmdyml, "r"))

    for i in range(len(wt.fieldnames)):
        if "I_" in wt.fieldtypes[i]:
            cmdDict[wt.fieldnames[i]] = wt[bindex][i]

    writeyaml(cmdDict, pathname+"/runraw.yml")
    ymlvars(pathname+"/runraw.yml", pathname+"/run.yml", coreFolder+"/"+pathname)
    os.remove(pathname+"/runraw.yml")

def clearQueue():
    global procQueue, lockQueue
    lockQueue = 1
    for usertoken in procQueue:
        if len(procQueue[usertoken])>0:
            command = procQueue[usertoken][0][0]
            pathname = procQueue[usertoken][0][1]
            bindex = procQueue[usertoken][0][2]
            procQueue[usertoken].pop(0)
            print(">> "+usertoken+" : "+command+" : "+pathname+" : {}".format(bindex))
            pathname = pathname[1:]
            wtname = re.split(".wtx", os.path.split(command)[1])[0]
            tstamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
            pathname = os.path.join(targetFolder, "log", wtname+"_"+tstamp+"-"+str(bindex))
            if not os.path.exists(pathname):
                if not os.path.exists(os.path.join(targetFolder, "log")):
                    os.mkdir(os.path.join(targetFolder, "log"))
                os.mkdir(pathname)

            result = ExecCWL(command, pathname, bindex)
            print("   Result: {}".format(result))
            if result>0:
               userstate.append(usertoken, '{}  <span class="bold"><span class="red">FAILED</span></span>'.format(pathname))
            else:
               userstate.append(usertoken, '{}  <span class="bold"><span class="green">OK</span></span>'.format(pathname))
            procCheck[usertoken].pop(0)
    lockQueue = 0

def myGlob(pathname):
    return glob.glob(pathname)

'''
    gRPC class: serves up functions to the clients
'''
class actionServer(action_pb2_grpc.ActionServicer):
    def makeyml(self, request, context):
        makeyml(request.pathname, request.command)
        return action_pb2.makeymlReply(mess="OK")

    def ExecCWL(self, request, context):
        print(request.cmdFile)
        return action_pb2.ExecCWLReply(result=ExecCWL(request.cmdFile, request.pathname))

    def isProc(self, request, context):
        if request.usertoken not in procCheck:
            return action_pb2.isFreeReply(result=False)
        if str(request.cmdFile)+str(request.bindex) in procCheck[request.usertoken]:
            return action_pb2.isFreeReply(result=True)
        return action_pb2.isFreeReply(result=False)

    def push(self, request, context):
        global lockQueue, procQueue
        while lockQueue>0:
          time.sleep(0.1)
        if request.usertoken not in procQueue:
            procQueue[request.usertoken] = []
            procCheck[request.usertoken] = []
        procQueue[request.usertoken].append([request.cmdFile, request.pathname, request.bindex])
        procCheck[request.usertoken].append(str(request.cmdFile)+str(request.bindex))
        return action_pb2.pushReply(mess="OK")

    def isFree(self, request, context):
        global procQueue
        if request.usertoken not in procQueue:
            procQueue[request.usertoken] = []
        if procQueue[request.usertoken]==[]:
            return action_pb2.isFreeReply(result=True)
        else:
            return action_pb2.isFreeReply(result=False)

    def glob(self, request, context):
        print(request.pathname)
        list = myGlob(request.pathname)
        for filename in list:
            yield action_pb2.globReply(filename=filename)

if __name__ == "__main__":
    serverinst = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    action_pb2_grpc.add_ActionServicer_to_server(actionServer(), serverinst)
    portnum = serverinst.add_insecure_port('[::]:7000')
    serverinst.start()
    print("Action server started on port {}".format(portnum))
    try:
        while True:
            clearQueue()
            time.sleep(1)
            sys.stdout.flush()
    except KeyboardInterrupt:
        serverinst.stop(0)
