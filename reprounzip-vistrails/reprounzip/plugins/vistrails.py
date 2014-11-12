# Copyright (C) 2014 New York University
# This file is part of ReproZip which is released under the Revised BSD License
# See file LICENSE for full license details.

"""VisTrails runner for reprounzip.

This file provides the --vistrails option that builds a VisTrails pipeline
alongside an unpacked experiment. Although you don't need it to generate the
.vt file, you will need VisTrails if you want to run it.

See http://www.vistrails.org/
"""

from __future__ import unicode_literals

import argparse
import base64
from datetime import datetime
import hashlib
import logging
import os
from reprounzip import signals
from rpaths import Path
import subprocess
import sys
import zipfile

from reprounzip.common import load_config, setup_logging
from reprounzip.main import __version__ as version
from reprounzip.utils import escape


class sha1(object):
    def __init__(self, arg=b''):
        self._hash = hashlib.sha1()
        if arg:
            self.update(arg)

    def update(self, arg):
        if not isinstance(arg, bytes):
            arg = arg.encode('ascii')
        self._hash.update(arg)

    def digest(self):
        """Returns the message digest as binary (type bytes).
        """
        return self._hash.digest()

    def hexdigest(self):
        """Returns the message digest as hexadecimal (type str).
        """
        return self._hash.hexdigest()


def hash_experiment_run(run):
    """Generates a unique id from a single run of an experiment.

    This is used to name the CLTools modules.
    """
    h = sha1()
    for input_name in sorted(run['input_files']):
        h.update('input %s\n' % input_name)
    for output_name in sorted(run['output_files']):
        h.update('output %s\n' % output_name)
    return base64.b64encode(h.digest(), b'@$')


def do_vistrails(target):
    """Create a VisTrails workflow that runs the experiment.

    This is called from signals after an experiment has been setup by any
    unpacker.
    """
    unpacker = signals.unpacker
    dot_vistrails = Path('~/.vistrails').expand_user()

    runs, packages, other_files = load_config(target / 'config.yml',
                                              canonical=True)
    for run in runs:
        module_name = write_cltools_module(run, dot_vistrails)

        # Writes VisTrails workflow
        bundle = target / 'vistrails.vt'
        logging.info("Writing VisTrails workflow %s...", bundle)
        vtdir = Path.tempdir(prefix='reprounzip_vistrails_')
        try:
            with vtdir.open('w', 'vistrail',
                            encoding='utf-8', newline='\n') as fp:
                vistrail = '''\
<vistrail id="" name="" version="1.0.4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.vistrails.org/vistrail.xsd">
  <action date="{date}" id="1" prevId="0" session="0" user="ReproUnzip">
    <add id="0" objectId="0" parentObjId="" parentObjType="" what="module">
      <module cache="1" id="0" name="{module_name}" namespace="" package="org.vistrails.vistrails.cltools" version="0.1.2" />
    </add>
    <add id="1" objectId="0" parentObjId="0" parentObjType="module" what="location">
      <location id="0" x="0.0" y="0.0" />
    </add>
    <add id="2" objectId="0" parentObjId="0" parentObjType="module" what="function">
      <function id="0" name="directory" pos="0" />
    </add>
    <add id="3" objectId="0" parentObjId="0" parentObjType="function" what="parameter">
      <parameter alias="" id="0" name="&lt;no description&gt;" pos="0" type="org.vistrails.vistrails.basic:String" val="{directory}" />
    </add>
    <add id="4" objectId="1" parentObjId="0" parentObjType="module" what="function">
      <function id="1" name="unpacker" pos="1" />
    </add>
    <add id="5" objectId="1" parentObjId="1" parentObjType="function" what="parameter">
      <parameter alias="" id="1" name="&lt;no description&gt;" pos="0" type="org.vistrails.vistrails.basic:String" val="{unpacker}" />
    </add>
  </action>
</vistrail>
'''
                vistrail = vistrail.format(date='2014-11-12 15:31:18',
                                           unpacker=unpacker,
                                           directory=target.absolute(),
                                           module_name=module_name)
                fp.write(vistrail)

            with bundle.open('wb') as fp:
                z = zipfile.ZipFile(fp, 'w')
                with vtdir.in_dir():
                    for path in Path('.').recursedir():
                        z.write(str(path))
                z.close()
        finally:
            vtdir.rmtree()


def write_cltools_module(run, dot_vistrails):
    input_files = run['input_files']
    output_files = run['output_files']

    module_name = 'reprounzip_%s' % hash_experiment_run(run)[:7]

    # Writes CLTools JSON definition
    (dot_vistrails / 'CLTools').mkdir(parents=True)
    cltools_module = (dot_vistrails / 'CLTools' / module_name) + '.clt'
    logging.info("Writing CLTools definition %s...", cltools_module)
    with cltools_module.open('w', encoding='utf-8', newline='\n') as fp:
        fp.write('{\n'
                 '    "_comment": "This file was generated by reprounzip '
                 '%(version)s at %(date)s",\n\n' % {
                     'version': version,
                     'date': datetime.now().isoformat()})
        # python -m reprounzip.plugins.vistrails
        fp.write('    "command": "%s",\n'
                 '    "args": [\n'
                 '        [\n'
                 '            "constant",\n'
                 '            "-m",\n'
                 '            "flag",\n'
                 '            {}\n'
                 '        ],\n'
                 '        [\n'
                 '            "constant",\n'
                 '            "reprounzip.plugins.vistrails",\n'
                 '            "flag",\n'
                 '            {}\n'
                 '        ],\n' % escape(sys.executable))
        # Unpacker
        fp.write('        [\n'
                 '            "input",\n'
                 '            "unpacker",\n'
                 '            "string",\n'
                 '            {}\n'
                 '        ],\n')
        # Target directory
        fp.write('        [\n'
                 '            "input",\n'
                 '            "directory",\n'
                 '            "string",\n'
                 '            {}\n'
                 '        ]%s\n' % (
                     ',' if input_files or output_files else ''))
        # Input files
        for i, input_name in enumerate(input_files):
            comma = ',' if i + 1 < len(input_files) or output_files else ''
            fp.write('        [\n'
                     '            "input",\n'
                     '            "input %(name)s",\n'
                     '            "file",\n'
                     '            {\n'
                     '                "flag": "--input-file",\n'
                     '                "prefix": "%(name)s:"\n'
                     '            }\n'
                     '        ]%(comma)s\n' % {
                         'name': escape(input_name),
                         'comma': comma})
        # Output files
        for i, output_name in enumerate(output_files):
            comma = ',' if i + 1 < len(output_files) else ''
            fp.write('        [\n'
                     '            "output",\n'
                     '            "output %(name)s",\n'
                     '            "file",\n'
                     '            {\n'
                     '                "flag": "--output-file",\n'
                     '                "prefix": "%(name)s:"\n'
                     '            }\n'
                     '        ]%(comma)s\n' % {
                         'name': escape(output_name),
                         'comma': comma})
        fp.write('    ],\n')
        # Use "std file processing" since VisTrails <=2.1.4 has a bug without
        # this (also, it's inefficient)
        fp.write('    "options": {\n'
                 '        "std_using_files": ""\n'
                 '    },\n')
        # Makes the module check for errors
        fp.write('    "return_code": 0,\n')
        # Enable 'stdout' port
        fp.write('    "stdout": [\n'
                 '        "stdout",\n'
                 '        "file",\n'
                 '        {}\n'
                 '    ]\n'
                 '}\n')

    return module_name


def setup_vistrails():
    """Setup the plugin.
    """
    signals.post_setup.subscribe(do_vistrails)


def run_from_vistrails():
    setup_logging('REPROUNZIP-VISTRAILS', logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('unpacker')
    parser.add_argument('directory')
    parser.add_argument('--input-file', action='append', default=[])
    parser.add_argument('--output-file', action='append', default=[])

    args = parser.parse_args()

    python = sys.executable
    rpuz = [python, '-m', 'reprounzip.main', args.unpacker]

    os.environ['REPROUNZIP_NON_INTERACTIVE'] = 'y'

    def cmd(lst):
        logging.info("cmd: %s", ' '.join(lst))
        subprocess.check_call(rpuz + lst,
                              cwd=args.directory)

    logging.info("reprounzip-vistrails calling reprounzip; dir=%s",
                 args.directory)

    # Sets up input files
    for input_file in args.input_file:
        input_name, filename = input_file.split(':', 1)
        cmd(['upload', '.',
             '%s:%s' % (filename, input_name)])

    # Runs
    cmd(['run', '.'])

    # Gets output files
    for output_file in args.output_file:
        output_name, filename = output_file.split(':', 1)
        cmd(['download', '.',
             '%s:%s' % (output_name, filename)])


if __name__ == '__main__':
    run_from_vistrails()
