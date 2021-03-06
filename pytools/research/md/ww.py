"""
Usefull utilities for the WW mutants projects
"""

from protolyze.tool.MSMBuilder import Builder, Cluster
from protolyze.db.results import WorkqueuePathFixer
import protolyze.weave as weave

import protolyze.db.results as dbresults

from weaver.dataset import MySQLDataSet, Query, And, Or

import os.path
import itertools
import functools


class Project(object):
    def __init__(self, number, hostname, mutant, dbname, dbtype):
        self.number   = number
        self.hostname = hostname
        self.mutant   = mutant
        self.dbname   = dbname
        self.dbtype   = dbtype

class DBAccess(object):
    def __init__(self, db=None, host=None, table=None, user=None, password=None):
        self.db       = db
        self.host     = host
        self.table    = table
        self.user     = user
        self.password = password

    def to_sqlalchemy_session_string(self, dbtype='mysql'):
        if type(self.user) is str and type(self.password) is str:
            auth = '%s:%s' % (self.user, self.password)
        else:
            auth = ''

        at = '@' if auth else ''

        sess_str = '%(type)s://%(auth)s%(at)s%(host)s/%(dbname)s' % {'type':dbtype,
                                                                     'auth':auth,
                                                                     'at':at,
                                                                     'host':self.host,
                                                                     'dbname':self.db}

        return sess_str


def get_projects(dbname = lambda proj_number: 'P10K%02d' % (proj_number - 10000),
                 dbaccess = DBAccess(),
                 dbtype = 'mysql'):

    def mkProject(n,v): return Project(n, dbaccess.host, v, dbname(n), dbtype)

    projects = map(lambda (k,v): mkProject(10000+k, v), [
            (0, 22), (1,22), (2, 22), (3, 22), (4, 22), (5, 14), (6, 22), (7, 22), (8, 22), 
            (9,14), (12,0), (13,1), (14,2),
            (15, 3), (16,4), (17, 5),
            (19, 7), (20, 8), (21, 9), (22, 10), (23, 11), (24, 12),
            (27,16),
            (30,19), (31,20), (32, 21), (33, 22), (34, 23),
            (38,27), (39, 28),
            (40, 22),
            (41, 14),
            ] + map(lambda p: (p, 22), range(42, 62))
                   )

    return projects

PROJECTS = get_projects()


def database(project, dbaccess=DBAccess(), file_path = lambda obj: obj.xtc):
    db = MySQLDataSet( host  = project.hostname,
                       name  = project.dbname,
                       table = dbaccess.table,
                       user  = dbaccess.user,
                       pswd  = dbaccess.password )
    db.file_path = file_path
    return db


def mutant_id(project):
    if type(project) is Project:
        return project.mutant
    elif type(project) is int or type(project) is long:
        mid = filter(lambda p: p.number == project, PROJECTS)
        if len(mid) == 1:
            return mid[0].mutant
        else:
            raise ValueError, 'Cannot find project with PID %s' % project
    else:
        raise ValueError, 'project must be %s or %s. Got %s = %s' % (Project, int, type(project), project)

NDX_ROOT = '/afs/crc.nd.edu/user/c/cabdulwa/Public/Research/md/ww/ndx/msmbuilder'
GMX_NDX_ROOT = '/afs/crc.nd.edu/user/c/cabdulwa/Public/Research/md/ww/ndx/gmx'
def ndx(name, project, ndx_root=NDX_ROOT):
    return os.path.join(ndx_root, '%d/%s' % (project.mutant, name))

FOLDED_ROOT = '/afs/crc.nd.edu/user/c/cabdulwa/Public/Research/md/ww/folded'
def psf(project, root=FOLDED_ROOT):
    mutantid = mutant_id(project)
    return os.path.join(root, '%d.psf' % mutantid)

def model_pdb(project, root=None):
    psffile = psf(project) if root is None else psf(project, root=root)
    return psffile.rsplit('.psf')[0] + '.pdb'


def get_paths(project, frames=None, limit=None, dbaccess=DBAccess, column='xtc', additional_and=None, additional_or=None):
    if column is 'xtc':
        file_path_fn = lambda obj: obj.xtc
        db = database(project, dbaccess=dbaccess, file_path = file_path_fn)

        if type(frames) is int:
            predicate = And(db.c.frames == frames, db.c.xtc % '%.xtc')
        else:
            predicate = And(db.c.xtc % '%.xtc')

    elif column is 'location':
        file_path_fn = lambda obj: obj.location
        db = database(project, dbaccess=dbaccess, file_path = file_path_fn)

        if type(frames) is int:
            predicate = And(db.c.frames == frames, db.c.location % '%.tar.bz2', db.c.xtc == None)
        else:
            predicate = And(db.c.location % '%.tar.bz2', db.c.xtc == None)

    if additional_and:
        predicate = And(predicate, additional_and(db))
    if additional_or:
        predicate = Or(predicate, additional_or(db))

    if isinstance(limit, int):
        q = Query(db, predicate, limit=limit ) 
    else:
        q = Query(db, predicate)

    wq_path_fixer = WorkqueuePathFixer()
    paths = itertools.imap( wq_path_fixer.fix, q )
    return list(paths)

def mk_trajlist(project, xtcs=True, tarfiles=True, convert=lambda obj:obj, tarfile_exists_filter=True, **kws):

    if xtcs is False and tarfiles is False:
        msg = 'mk_trajlist: kwargs: xtcs, tarfiles cannot both be False'
        print msg
        raise ValueError, msg


    if xtcs is True:
        print 'Getting xtcs'
        for xtc_count, xtc in enumerate(get_xtcs(project, **kws)):
            yield xtc
        count = xtc_count + 1
    else:
        print 'Skipping xtcs'
        count = 0

    limit = kws.pop('limit', None)
    if type(limit) is int and count < limit:
        new_limit   = limit - count
        do_tarfiles = tarfiles and new_limit > 0 and True
    elif limit is None:
        new_limit   = limit
        do_tarfiles = True
    else:
        print 'Skipping tarfiles'
        do_tarfiles = False

    if do_tarfiles is True:
        print 'Getting tarfiles'
        for tarfile in get_locations(project, limit=new_limit, **kws):
            xtc, cmd = convert(tarfile)
            result   = '%s %s' % (xtc, ' '.join(cmd))
            if tarfile_exists_filter:
                if os.path.exists(tarfile):
                    count += 1
                    yield result
            else:
                count += 1
                yield result

    print 'Trajectories in listing:', count


def get_xtcs(*args, **kws):
    return get_paths(*args, column='xtc', **kws)

def get_locations(*args, **kws):
    return get_paths(*args, column='location', **kws)


def msm_path(msm_root, ndx_name, msm_on=None):
    root = os.path.join(msm_root, ndx_name)
    if isinstance(msm_on, Project):
        typ = 'singleton'
        name = msm_on.dbname
    elif isinstance(msm_on, list) and all(map(lambda o: isinstance(o, project), msm_on)):
        typ = 'combined'
        name = '-'.join(map(lambda p: p.dbname, msm_on))
    else:
        raise TypeError, "msm_path: 'msm_on' kwarg needs to be either a Project or a list of projects"

    return os.path.join(root, typ, name)


PROTOTOOLS_SFX = '/afs/crc.nd.edu/user/c/cabdulwa/prototools.git/starch'
def cmd_convert_workunit_to_xtc(path, dest, dcdname='ww.dcd', prototools=PROTOTOOLS_SFX):
    """returns the command to convert the path into an xtc"""

    convert = os.path.join(prototools, 'ConvertFaHTarballToXTC.sfx')

    wu = dbresults.Workunit.from_path(path)

    proj = filter(lambda p: p.number == wu.get_project_id(), get_projects())

    if len(proj) > 0:
        fn = weave.Tool.ConvertFaHTarballToXTC(convert, dcdname, psf(proj[0]), dest)
        cmd = [convert] + fn.cmd_args
        cmd.append(path)

        target = os.path.join(dest, wu.to_path())

        return target, cmd
    else:
        raise IndexError, 'No project known for workunit: %s' % path
