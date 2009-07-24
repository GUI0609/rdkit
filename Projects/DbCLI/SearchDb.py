# $Id$
#
#  Copyright (c) 2007, Novartis Institutes for BioMedical Research Inc.
#  All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: 
#
#     * Redistributions of source code must retain the above copyright 
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following 
#       disclaimer in the documentation and/or other materials provided 
#       with the distribution.
#     * Neither the name of Novartis Institutes for BioMedical Research Inc. 
#       nor the names of its contributors may be used to endorse or promote 
#       products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#  Created by Greg Landrum, July 2007
#
_version = "0.12.0"
_usage="""
 SearchDb [optional arguments] <sdfilename>

     The sd filename argument can be either an SD file or an MDL mol 
     file.
     

  NOTES:

    - The property names may have been altered on loading the
      database.  Any non-alphanumeric character in a property name
      will be replaced with '_'. e.g."Gold.Goldscore.Constraint.Score" becomes
      "Gold_Goldscore_Constraint_Score".

    - Property names are not case sensitive in the database.

 """
from rdkit import RDConfig
from rdkit.Dbase.DbConnection import DbConnect

from rdkit.RDLogger import logger
logger=logger()
import zlib
from rdkit import Chem

from rdkit.Chem.MolDb.FingerprintUtils import supportedSimilarityMethods,BuildSigFactory,DepickleFP,LayeredOptions
from rdkit.Chem.MolDb import FingerprintUtils

from rdkit import DataStructs


def GetNeighborLists(probes,topN,pool,
                     simMetric=DataStructs.DiceSimilarity,
                     silent=False):
  probeFps = [x[1] for x in probes]
  validProbes = [x for x in range(len(probeFps)) if probeFps[x] is not None]
  validFps=[probeFps[x] for x in validProbes]
  from rdkit.DataStructs.TopNContainer import TopNContainer
  nbrLists = [TopNContainer(topN) for x in range(len(probeFps))]

  nDone=0
  for nm,fp in pool:
    nDone+=1
    if not silent and not nDone%1000: logger.info('  searched %d rows'%nDone)
    if(simMetric==DataStructs.DiceSimilarity):
      scores = DataStructs.BulkDiceSimilarity(fp,validFps)
      for i,score in enumerate(scores):
        nbrLists[validProbes[i]].Insert(score,nm)
    elif(simMetric==DataStructs.TanimotoSimilarity):
      scores = DataStructs.BulkTanimotoSimilarity(fp,validFps)
      for i,score in enumerate(scores):
        nbrLists[validProbes[i]].Insert(score,nm)
    else:
      for i in range(len(probeFps)):
        pfp = probeFps[i]
        if pfp is not None:
          score = simMetric(probeFps[i],fp)
          nbrLists[i].Insert(score,nm)
  return nbrLists

def GetMolsFromSmilesFile(dataFilename,errFile,nameProp):
  dataFile=file(dataFilename,'r')
  for idx,line in enumerate(dataFile):
    try:
      smi,nm = line.strip().split(' ')
    except:
      continue
    try:
      m = Chem.MolFromSmiles(smi)
    except:
      m=None
    if not m:
      if errfile:
        print >>errFile,idx,nm,smi
      continue
    yield (nm,smi,m)

def GetMolsFromSDFile(dataFilename,errFile,nameProp):
  suppl = Chem.SDMolSupplier(dataFilename)

  for idx,m in enumerate(suppl):
    if not m:
      if errFile:
        if hasattr(suppl,'GetItemText'):
          d = suppl.GetItemText(idx)
          errFile.write(d)
        else:
          logger.warning('full error file support not complete')
      continue
    smi = Chem.MolToSmiles(m,True)
    if m.HasProp(nameProp):
      nm = m.GetProp(nameProp)
      if not nm:
        logger.warning('molecule found with empty name property')
    else:
      nm = 'Mol_%d'%(idx+1)
    yield nm,smi,m


def RunSearch(options,queryFilename):
  global sigFactory
  if options.similarityType=='AtomPairs':
    fpBuilder=FingerprintUtils.BuildAtomPairFP
    simMetric=DataStructs.DiceSimilarity
    dbName = os.path.join(options.dbDir,options.pairDbName)
    fpTableName = options.pairTableName
    fpColName = options.pairColName
  elif options.similarityType=='TopologicalTorsions':
    fpBuilder=FingerprintUtils.BuildTorsionsFP
    simMetric=DataStructs.DiceSimilarity
    dbName = os.path.join(options.dbDir,options.torsionsDbName)
    fpTableName = options.torsionsTableName
    fpColName = options.torsionsColName
  elif options.similarityType=='RDK':
    fpBuilder=FingerprintUtils.BuildRDKitFP
    simMetric=DataStructs.FingerprintSimilarity
    dbName = os.path.join(options.dbDir,options.fpDbName)
    fpTableName = options.fpTableName
    if not options.fpColName:
      options.fpColName='rdkfp'
    fpColName = options.fpColName
  elif options.similarityType=='Pharm2D':
    fpBuilder=FingerprintUtils.BuildPharm2DFP
    simMetric=DataStructs.DiceSimilarity
    dbName = os.path.join(options.dbDir,options.fpDbName)
    fpTableName = options.pharm2DTableName
    if not options.fpColName:
      options.fpColName='pharm2dfp'
    fpColName = options.fpColName
    FingerprintUtils.sigFactory = BuildSigFactory(options)
  elif options.similarityType=='Gobbi2D':
    from rdkit.Chem.Pharm2D import Gobbi_Pharm2D
    fpBuilder=FingerprintUtils.BuildPharm2DFP
    simMetric=DataStructs.TanimotoSimilarity
    dbName = os.path.join(options.dbDir,options.fpDbName)
    fpTableName = options.gobbi2DTableName
    if not options.fpColName:
      options.fpColName='gobbi2dfp'
    fpColName = options.fpColName
    FingerprintUtils.sigFactory = Gobbi_Pharm2D.factory
  elif options.similarityType=='Morgan':
    fpBuilder=FingerprintUtils.BuildMorganFP
    simMetric=DataStructs.DiceSimilarity
    dbName = os.path.join(options.dbDir,options.morganFpDbName)
    fpTableName = options.morganFpTableName
    fpColName = options.morganFpColName

  if options.smilesQuery:
    mol=Chem.MolFromSmiles(options.smilesQuery)
    if not mol:
      logger.error('could not build query molecule from smiles "%s"'%options.smilesQuery)
      sys.exit(-1)
    options.queryMol = mol
  elif options.smartsQuery:
    mol=Chem.MolFromSmarts(options.smartsQuery)
    if not mol:
      logger.error('could not build query molecule from smarts "%s"'%options.smartsQuery)
      sys.exit(-1)
    options.queryMol = mol

  if options.outF=='-':
    outF=sys.stdout
  else:
    outF = file(options.outF,'w+')
  
  molsOut=False
  if options.sdfOut:
    molsOut=True
    if options.sdfOut=='-':
      sdfOut=sys.stdout
    else:
      sdfOut = file(options.sdfOut,'w+')
  else:
    sdfOut=None
  if options.smilesOut:
    molsOut=True
    if options.smilesOut=='-':
      smilesOut=sys.stdout
    else:
      smilesOut = file(options.smilesOut,'w+')
  else:
    smilesOut=None

  if queryFilename:
    try:
      tmpF = file(queryFilename,'r')
    except IOError:
      logger.error('could not open query file %s'%queryFilename)
      sys.exit(1)

    if options.molFormat=='smiles':
      func=GetMolsFromSmilesFile
    elif options.molFormat=='sdf':
      func=GetMolsFromSDFile

    if not options.silent:
      msg='Reading query molecules'
      if fpBuilder: msg+=' and generating fingerprints'
      logger.info(msg)
    probes=[]
    i=0
    nms=[]
    for nm,smi,mol in func(queryFilename,None,options.nameProp):
      i+=1
      nms.append(nm)
      if not mol:
        logger.error('query molecule %d could not be built'%(i))
        probes.append((None,None))
        continue
      if fpBuilder:
        probes.append((mol,fpBuilder(mol)))
      else:
        probes.append((mol,None))
      if not options.silent and not i%1000:
        logger.info("  done %d"%i)
  else:
    probes=None

  conn=None
  idName = options.molIdName
  ids=None
  if options.propQuery or options.queryMol:
    molDbName = os.path.join(options.dbDir,options.molDbName)
    conn = DbConnect(molDbName)
    curs = conn.GetCursor()
    if options.queryMol:
      if not options.silent: logger.info('Doing substructure query')
      if options.propQuery:
        where='where %s'%options.propQuery
      else:
        where=''
      if not options.silent:
        curs.execute('select count(*) from molecules %(where)s'%locals())
        nToDo = curs.fetchone()[0]

      join=''        
      doSubstructFPs=False
      fpDbName = os.path.join(options.dbDir,options.fpDbName)
      if os.path.exists(fpDbName):
        curs.execute("attach database '%s' as fpdb"%(fpDbName))
        try:
          curs.execute('select * from fpdb.%s limit 1'%options.layeredTableName)
        except:
          pass
        else:
          doSubstructFPs=True
          join = 'join fpdb.%s using (%s)'%(options.layeredTableName,idName)
          query = LayeredOptions.GetQueryText(options.queryMol)
          if query:
            if not where:
              where='where'
            else:
              where += ' and'
            where += ' '+query

      cmd = 'select %(idName)s,molpkl from molecules %(join)s %(where)s'%locals()
      curs.execute(cmd)
      row=curs.fetchone()
      nDone=0
      ids=[]
      while row:
        id,molpkl = row
        if not options.zipMols:
          m = Chem.Mol(str(molpkl))
        else:
          m = Chem.Mol(zlib.decompress(str(molpkl)))
        matched=m.HasSubstructMatch(options.queryMol)
        if options.negateQuery:
          matched = not matched
        if matched:
          ids.append(id)
        nDone+=1
        if not options.silent and not nDone%500:
          if not doSubstructFPs:
            logger.info('  searched %d (of %d) molecules; %d hits so far'%(nDone,nToDo,len(ids)))
          else:
            logger.info('  searched through %d molecules; %d hits so far'%(nDone,len(ids)))
        row=curs.fetchone()
      if not options.silent and doSubstructFPs:
        nFiltered = nToDo-nDone
        logger.info('   Fingerprint screenout rate: %d of %d (%%%.2f)'%(nFiltered,nToDo,100.*nFiltered/nToDo))

    elif options.propQuery:
      if not options.silent: logger.info('Doing property query')
      propQuery=options.propQuery.split(';')[0]
      curs.execute('select %(idName)s from molecules where %(propQuery)s'%locals())
      ids = [str(x[0]) for x in curs.fetchall()]
    if not options.silent:
      logger.info('Found %d molecules matching the query'%(len(ids)))

  t1=time.time()
  if probes:
    if not options.silent: logger.info('Finding Neighbors')
    conn = DbConnect(dbName)
    curs = conn.GetCursor()
    if ids:
      ids = [(x,) for x in ids]
      curs.execute('create temporary table _tmpTbl (%(idName)s varchar)'%locals())
      curs.executemany('insert into _tmpTbl values (?)',ids)
      join='join  _tmpTbl using (%(idName)s)'%locals()
    else:
      join=''

    curs.execute('select %(idName)s,%(fpColName)s from %(fpTableName)s %(join)s'%locals())
    def poolFromCurs(curs,similarityMethod):
      row = curs.fetchone()
      while row:
        nm,pkl = row
        fp = DepickleFP(str(pkl),similarityMethod)
        yield (nm,fp)
        row = curs.fetchone()
    topNLists = GetNeighborLists(probes,options.topN,poolFromCurs(curs,options.similarityType),
                                 simMetric=simMetric)

    uniqIds=set()
    nbrLists = {}
    for i,nm in enumerate(nms):
      topNLists[i].reverse()
      scores=topNLists[i].GetPts()
      nbrNames = topNLists[i].GetExtras()
      nbrs = []
      for j,nbrNm in enumerate(nbrNames):
        if nbrNm is None:
          break
        else:
          uniqIds.add(nbrNm)
          nbrs.append((nbrNm,scores[j]))
      nbrLists[(i,nm)] = nbrs
    t2=time.time()
    if not options.silent: logger.info('The search took %.1f seconds'%(t2-t1))
    
    if not options.silent: logger.info('Creating output')
    ks = nbrLists.keys()
    ks.sort()
    if not options.transpose:
      for i,nm in ks:
        nbrs= nbrLists[(i,nm)]
        nbrTxt=options.outputDelim.join([nm]+['%s%s%.3f'%(x,options.outputDelim,y) for x,y in nbrs])
        print >>outF,nbrTxt
    else:
      labels = ['%s%sSimilarity'%(x[1],options.outputDelim) for x in ks]
      print >>outF,options.outputDelim.join(labels)
      for i in range(options.topN):
        outL = []
        for idx,nm in ks:
          nbr = nbrLists[(idx,nm)][i]
          outL.append(nbr[0])
          outL.append('%.3f'%nbr[1])
        print >>outF,options.outputDelim.join(outL)
    ids = list(uniqIds)
  else:
    if not options.silent: logger.info('Creating output')
    print >>outF,'\n'.join(ids)
  if molsOut and ids:
    molDbName = os.path.join(options.dbDir,options.molDbName)
    conn = DbConnect(molDbName)
    cns = [x.lower() for x in conn.GetColumnNames('molecules')]
    if cns[0]=='guid':
      # from sqlalchemy, ditch it:
      del cns[0]
    if cns[-1]!='molpkl':
      cns.remove('molpkl')
      cns.append('molpkl')

    curs = conn.GetCursor()
    ids = [(x,) for x in ids]
    curs.execute('create temporary table _tmpTbl (%(idName)s varchar)'%locals())
    curs.executemany('insert into _tmpTbl values (?)',ids)
    cnText=','.join(cns)
    curs.execute('select %(cnText)s from molecules join _tmpTbl using (%(idName)s)'%locals())

    row=curs.fetchone()
    molD = {}
    while row:
      row = list(row)
      pkl = row[-1]
      m = Chem.Mol(str(pkl))
      nm = str(row[0])
      if sdfOut:
        m.SetProp('_Name',nm)
        print >>sdfOut,Chem.MolToMolBlock(m)
        for i in range(1,len(cns)-1):
          pn = cns[i]
          pv = str(row[i])
          print >>sdfOut,'> <%s>\n%s\n'%(pn,pv)
        print >>sdfOut,'$$$$'
      if smilesOut :
        smi=Chem.MolToSmiles(m,options.chiralSmiles)        
      if smilesOut:
        print >>smilesOut,'%s %s'%(smi,str(row[0]))
      row=curs.fetchone()
  if not options.silent: logger.info('Done!')

# ---- ---- ---- ----  ---- ---- ---- ----  ---- ---- ---- ----  ---- ---- ---- ---- 
import os
from optparse import OptionParser
parser=OptionParser(_usage,version='%prog '+_version)
parser.add_option('--dbDir',default='/db/camm/CURRENT/rdk_db',
                  help='name of the directory containing the database information. The default is %default')
parser.add_option('--molDbName',default='Compounds.sqlt',
                  help='name of the molecule database')
parser.add_option('--molIdName',default='compound_id',
                  help='name of the database key column')
parser.add_option('--regName',default='molecules',
                  help='name of the molecular registry table')
parser.add_option('--pairDbName',default='AtomPairs.sqlt',
                  help='name of the atom pairs database')
parser.add_option('--pairTableName',default='atompairs',
                  help='name of the atom pairs table')
parser.add_option('--pairColName',default='atompairfp',
                  help='name of the atom pair column')
parser.add_option('--torsionsDbName',default='AtomPairs.sqlt',
                  help='name of the topological torsions database (usually the same as the atom pairs database)')
parser.add_option('--torsionsTableName',default='atompairs',
                  help='name of the topological torsions table (usually the same as the atom pairs table)')
parser.add_option('--torsionsColName',default='torsionfp',
                  help='name of the atom pair column')
parser.add_option('--fpDbName',default='Fingerprints.sqlt',
                  help='name of the 2D fingerprints database')
parser.add_option('--fpTableName',default='rdkitfps',
                  help='name of the 2D fingerprints table')
parser.add_option('--layeredTableName',default='layeredfps',
                  help='name of the layered fingerprints table')
parser.add_option('--fpColName',default='',
                  help='name of the 2D fingerprint column, a sensible default is used')
parser.add_option('--descrDbName',default='Descriptors.sqlt',
                  help='name of the descriptor database')
parser.add_option('--descrTableName',default='descriptors_v1',
                  help='name of the descriptor table')
parser.add_option('--descriptorCalcFilename',default=os.path.join(RDConfig.RDBaseDir,'Projects',
                                                                  'DbCLI','moe_like.dsc'),
                  help='name of the file containing the descriptor calculator')
parser.add_option('--outputDelim',default=',',
                  help='the delimiter for the output file. The default is %default')
parser.add_option('--topN',default=20,type='int',
                  help='the number of neighbors to keep for each query compound. The default is %default')

parser.add_option('--outF','--outFile',default='-',
                  help='The name of the output file. The default is the console (stdout).')

parser.add_option('--transpose',default=False,action="store_true",
                  help='print the results out in a transposed form: e.g. neighbors in rows and probe compounds in columns')

parser.add_option('--molFormat',default='sdf',choices=('smiles','sdf'),
                  help='specify the format of the input file')
parser.add_option('--nameProp',default='_Name',
                  help='specify the SD property to be used for the molecule names. Default is to use the mol block name')

parser.add_option('--smartsQuery','--smarts','--sma',default='',
                  help='provide a SMARTS to be used as a substructure query')
parser.add_option('--smilesQuery','--smiles','--smi',default='',
                  help='provide a SMILES to be used as a substructure query')
parser.add_option('--negateQuery','--negate',default=False,action='store_true',
                  help='negate the results of the smarts query.')
parser.add_option('--propQuery','--query','-q',default='',
                  help='provide a property query (see the NOTE about property names)')

parser.add_option('--sdfOut','--sdOut',default='',
                  help='export an SD file with the matching molecules')
parser.add_option('--smilesOut','--smiOut',default='',
                  help='export a smiles file with the matching molecules')
parser.add_option('--nonchiralSmiles',dest='chiralSmiles',default=True,action='store_false',
                  help='do not use chiral SMILES in the output')
parser.add_option('--silent',default=False,action='store_true',
                  help='Do not generate status messages.')

parser.add_option('--zipMols','--zip',default=False,action='store_true',
                  help='read compressed mols from the database')

parser.add_option('--pharm2DTableName',default='pharm2dfps',
                  help='name of the Pharm2D fingerprints table')
parser.add_option('--fdefFile','--fdef',
                  default=os.path.join(RDConfig.RDDataDir,'Novartis1.fdef'),
                  help='provide the name of the fdef file to use for 2d pharmacophores')
parser.add_option('--gobbi2DTableName',default='gobbi2dfps',
                  help='name of the Gobbi2D fingerprints table')

parser.add_option('--similarityType','--simType','--sim',
                  default='RDK',choices=supportedSimilarityMethods,
                  help='Choose the type of similarity to use, possible values: RDK, AtomPairs, TopologicalTorsions, Pharm2D, Gobbi2D, Morgan. The default is %default')

parser.add_option('--morganFpDbName',default='Fingerprints.sqlt',
                  help='name of the morgan fingerprints database')
parser.add_option('--morganFpTableName',default='morganfps',
                  help='name of the morgan fingerprints table')
parser.add_option('--morganFpColName',default='morganfp',
                  help='name of the morgan fingerprint column')


if __name__=='__main__':
  import sys,getopt,time
  
  options,args = parser.parse_args()
  if len(args)!=1 and not (options.smilesQuery or options.smartsQuery or options.propQuery):
    parser.error('please either provide a query filename argument or do a data or smarts query')

  if len(args):
    queryFilename=args[0]
  else:
    queryFilename=None
  options.queryMol=None
  RunSearch(options,queryFilename)
