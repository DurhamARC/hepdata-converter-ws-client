# -*- encoding: utf-8 -*-
import base64
import json
import os
import requests
import tarfile
import tempfile
import shutil
from io import BytesIO
from builtins import str as text
from future.utils import raise_from

__author__ = 'Michał Szostak'

ARCHIVE_NAME = 'hepdata-converter-ws-data'


class Error(Exception):
    """Generic exception for hepdata_converter_ws_client"""
    pass


def convert(url, input, output=None, options={}, id=None, extract=True, timeout=600):
    """Wrapper function around requests library providing easy way to interact
    with hepdata-converter-ws (web services).

    :param url: path to server hosting hepdata-converter-ws (web services) - url has to point to root server
    (not ```/convert``` or any other specific route) just http(s)://address:port
    :type url: str

    :param input: Input, can be either path (str / unicode) to the file / directory that should be converted, or
    fileobject containing data with the content of the file that should be converted

    :type input: str / unicode / fileobject
    :param output: Output, can be either path (str / unicode) to the file / directory to which output should be written
    (in this case it will be automatically extracted, extract argument must be True), fileobject (in this case extract
    flag must be False, the response tar.gz content will be written to output fileobject) or None (not specified).
    If output is not specified extract flag is not taken into consideration and function returns content of the requested
    tar.gz file.

    :type output: str / unicode / fileobject

    :param options: Options passed to the converter - the same as the ones accepted by hepdata_converter.convert
    function (https://github.com/HEPData/hepdata-converter). Most basic key / values are:
    'input_format': 'yaml'
    'output_format': 'root'

    if not output_format has been specified the default is YAML
    if not input_format has been specified the default is YAML

    :type options: dict

    :param id: used for caching purposes (can be any object that can be turned into string) - if two convert calls
    have the same ID and output types same output will be returned. Because of this if IDs are equal it implies input
    files equality
    :type id: str / int

    :param extract: If set to True the requested tar.gz will be extracted to directory specified in output. If set to
    False requested tar.gz file fill be written to output. If no output has been specified this attribute is not taken
    into account.
    IMPORTANT if output is a file object (not a path) extract must be set to False
    :type extract: bool

    :param timeout: the time after which the request to the webservice will be cancelled. Defaults to 600s.
    :type timeout: int

    :raise ValueError: if input values are not sane ValueError is raised

    :raise Error: if the request to the server fails or times out

    :rtype : str Binary data
    :return: Binary data containing tar.gz return type. value is returned from this function if and only if no output
    has been specified
    """
    input_stream = BytesIO()
    output_defined = output is not None
    if not output_defined:
        extract = False
        output = BytesIO()

    archive_name = options.get('filename', ARCHIVE_NAME)

    # input is a path, treat is as such
    if isinstance(input, (str, text)):
        assert os.path.exists(input)

        with tarfile.open(mode='w:gz', fileobj=input_stream) as tar:
            tar.add(input, arcname=archive_name)
    elif hasattr(input, 'read'):
        with tarfile.open(mode='w:gz', fileobj=input_stream) as tar:
            info = tarfile.TarInfo(archive_name)
            input.seek(0, os.SEEK_END)
            info.size = input.tell()
            input.seek(0)
            tar.addfile(info, fileobj=input)
    else:
        raise ValueError('input is not path or file object!')

    inputdata = input_stream.getvalue()

    data = {'input': base64.b64encode(inputdata).decode('utf-8'),
            'options': options}

    if id:
        data['id'] = id

    try:
        r = requests.get(url + '/convert',
                         data=json.dumps(data),
                         headers={'Content-type': 'application/json',
                                  'Accept': 'application/x-gzip'},
                         timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise_from(Error('Request to %s failed' % url), e)

    error_occurred = False
    try:
        tarfile.open('r:gz', fileobj=BytesIO(r.content)).close()
    except tarfile.ReadError:
        error_occurred = True

    if extract and not error_occurred:
        if not isinstance(output, (str, text)):
            raise ValueError('if extract=True then output must be path')

        tmp_dir = tempfile.mkdtemp(suffix='hdc')
        try:
            with tarfile.open('r:gz', fileobj=BytesIO(r.content)) as tar:
                tar.extractall(tmp_dir)
            content = os.listdir(tmp_dir)[0]
            shutil.move(os.path.join(tmp_dir, content), output)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        if isinstance(output, (str, text)):
            with open(output, 'wb') as f:
                f.write(r.content)
        elif hasattr(output, 'write'):
            output.write(r.content)
        else:
            raise ValueError('output is not path or file object')

    if not output_defined:
        return output.getvalue()
    elif error_occurred:
        return False
    else:
        return True
