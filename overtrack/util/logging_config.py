import inspect
import logging
import logging.config
import os
import socket
import sys
import time
from collections import defaultdict
from threading import Thread
from typing import Callable, Optional, Sequence, Mapping, DefaultDict, Tuple, Dict, Union, \
    Any, List, TYPE_CHECKING, no_type_check

if TYPE_CHECKING:
    from mypy_extensions import TypedDict
    LogConfig = TypedDict(
        'LogConfig',
        {
            'level': str,
            'formatter': str,
            'class': str,
            'filename': str,
            'maxBytes': int,
            'backupCount': int,
            'delay': bool
        },
        total=False
    )
    UploadLogsSettingsType = TypedDict(
        'UploadLogsSettingsType',
        {
            'write_to_file': bool,
            'upload_func': Callable[[str, str], None],
            'args': Tuple[str, str]
        },
        total=False
    )
else:
    LogConfig = Dict
    UploadLogsSettingsType = Dict


LOG_FORMAT = '[%(asctime)16s | %(levelname)8s | %(name)24s | %(filename)s:%(lineno)s %(funcName)s() ] %(message)s'


def intermittent_log(
        logger: logging.Logger,
        line: str,
        frequency: float=60,
        level: int=logging.INFO,
        negative_level: Optional[int]=None,
        _last_logged: DefaultDict[Tuple[str, int], float]=defaultdict(float),
        caller_extra_id: Any = None) -> None:
    try:
        caller = inspect.stack()[1]
        output = negative_level
        frame_id = caller.filename, caller.lineno, caller_extra_id
        if time.time() - _last_logged[frame_id] > frequency:
            _last_logged[frame_id] = time.time()
            output = level
        if output and logger.isEnabledFor(output):
            co = caller.frame.f_code
            fn, lno, func, sinfo = (co.co_filename, caller.frame.f_lineno, co.co_name, None)
            record = logger.makeRecord(logger.name, output, str(fn), lno, line, {}, None, func, None, sinfo)
            logger.handle(record)
    except:
        # noinspection PyProtectedMember
        logger.log(level, line, ())


upload_logs_settings: UploadLogsSettingsType = {
    'write_to_file': False,
}


def config_logger(
        name: str,
        level: int=logging.INFO,

        write_to_file: bool=True,

        use_datadog: bool=False,
        use_stackdriver: bool=False,

        stackdriver_level: int=logging.INFO,

        use_stackdriver_error: bool=False,

        upload_func: Optional[Callable[[str, str], None]]=None,
        upload_frequency: Optional[float]=None) -> None:

    logger = logging.getLogger()

    handlers: Dict[str, LogConfig] = {
        'default': {
            'level': logging.getLevelName(level),
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        }
    }
    if write_to_file:
        os.makedirs('logs', exist_ok=True)
        handlers.update({
            'file': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': f'logs/{name}.log',
                'maxBytes': 1024 * 1024 * 100,
                'backupCount': 3,
                'delay': True
            },
            'file_debug': {
                'level': 'DEBUG',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': f'logs/{name}.debug.log',
                'maxBytes': 1024 * 1024 * 100,
                'backupCount': 3,
                'delay': True
            },
            'web_access': {
                'level': 'DEBUG',
                'formatter': '',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'logs/access.log',
                'maxBytes': 1024,
                'backupCount': 0,
                'delay': True
            }
        })
    else:
        handlers.update({
            'file': {
                'class': 'logging.NullHandler',
            },
            'file_debug': {
                'class': 'logging.NullHandler',
            },
            'web_access': {
                'class': 'logging.NullHandler',
            }
        })

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': LOG_FORMAT
            },
        },
        'handlers': handlers,
        'loggers': {
            '': {
                'handlers': ['default', 'file', 'file_debug'],
                'level': 'DEBUG',
                'propagate': True
            },

            'cherrypy.access': {
                'handlers': ['web_access'],
                'level': 'WARN',
                'propagate': False
            },
            'sanic.access': {
                'handlers': ['web_access'],
                'level': 'WARN',
                'propagate': False
            },

            'libav.AVBSFContext': {
                'handlers': ['default', 'file', 'file_debug'],
                'level': 'CRITICAL',
                'propagate': False
            },
            'libav.swscaler': {
                'handlers': ['default', 'file', 'file_debug'],
                'level': 'CRITICAL',
                'propagate': False
            },

            'datadog.api': {
                'handlers': [],
                'level': 'ERROR',
                'propagate': False
            },
        }
    })

    if use_stackdriver:
        import google.cloud.logging
        from google.cloud.logging.handlers import CloudLoggingHandler
        from google.cloud.logging.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS

        # noinspection PyUnresolvedReferences
        client = google.cloud.logging.Client()
        # client.setup_logging()

        handler = CloudLoggingHandler(client, name=name)
        handler.setLevel(stackdriver_level)
        logger.addHandler(handler)
        for logger_name in EXCLUDED_LOGGER_DEFAULTS + ('urllib3.connectionpool', ):
            exclude = logging.getLogger(logger_name)
            exclude.propagate = False
            # exclude.addHandler(logging.StreamHandler())

    if use_stackdriver_error:
        from google.cloud import error_reporting
        client = error_reporting.Client()

    if use_datadog:
        import datadog
        from datadog_logger import DatadogLogHandler
        datadog.initialize(api_key=os.environ['DATADOG_API_KEY'], app_key=os.environ['DATADOG_APP_KEY'])
        datadog_handler = DatadogLogHandler(
            tags=[
                f'host:{socket.gethostname()}',
                f'pid:{os.getpid()}',
                f'stack:{name}',
                'type:log'],
            mentions=[],
            level=logging.INFO
        )
        logger.addHandler(datadog_handler)

    for _ in range(3):
        logger.info('')
    logger.info(f'Command: "{" ".join(sys.argv)}", pid={os.getpid()}, name={name}')
    if use_stackdriver:
        logger.info(f'Connected to google cloud logging. Using name="{name}". Logging class: {logging.getLoggerClass()}')

    upload_logs_settings['write_to_file'] = write_to_file
    if write_to_file and upload_func and upload_frequency:
        upload_logs_settings['upload_func'] = upload_func
        file: str = handlers['file']['filename']
        file_debug: str = handlers['file_debug']['filename']
        # noinspection PyTypeChecker
        upload_logs_settings['args'] = file, file_debug

        def upload_loop() -> None:
            while True:
                assert upload_frequency
                assert upload_func
                time.sleep(upload_frequency)
                upload_func(handlers['file']['filename'], handlers['file_debug']['filename'])
        logger.info(f'Uploading log files every {upload_frequency}s')
        Thread(target=upload_loop, daemon=True).start()

    # hsh = hashlib.md5()
    # modules = [
    #     m.__file__ for m in globals().values() if
    #     isinstance(m, types.ModuleType) and
    #     hasattr(m, '__file__')
    # ]
    # modules.append(__file__)
    # for mod in sorted(modules):
    #     with open(mod, 'rb') as f:
    #         hsh.update(f.read())
    # logger.info(f'Modules hash: {hsh.hexdigest()}')


def finish_logging() -> None:
    if upload_logs_settings.get('write_to_file') and upload_logs_settings.get('upload_func') and upload_logs_settings.get('args'):
        upload_logs_settings['upload_func'](*upload_logs_settings['args'])


sentry_logger = logging.getLogger('object_to_json')


def patch_sentry_locals_capture() -> None:
    import sentry_sdk.utils
    from overtrack.frame import Frame

    @no_type_check
    def object_to_json(obj: object) -> Union[str, Dict[str, Any], List[Union[str, Dict, List]]]:

        if (isinstance(obj, bytes) or isinstance(obj, str)) and len(obj) > 128:
            return repr(obj[:128]) + f'...{len(obj) - 128}'

        def _walk(obji: object, depth: int) -> Union[str, Dict[str, Any], List[Union[str, Dict, List]]]:
            if depth < 4:
                if isinstance(obji, Frame):
                    return {'timestamp': obji.timestamp}
                if isinstance(obji, list) and len(obji) > 2 and isinstance(obji[0], Frame) and isinstance(obji[-1], Frame):
                    frames: List[Frame] = obji
                    return [_walk(frames[0], depth), f'...<{len(frames)-2}>...', _walk(frames[-1], depth)]
                if isinstance(obji, Sequence) and not isinstance(obji, (bytes, str)):
                    return [_walk(x, depth + 1) for x in obji]
                if isinstance(obji, Mapping):
                    return {sentry_sdk.utils.safe_str(k): _walk(v, depth + 1) for k, v in obji.items()}
            return sentry_sdk.utils.safe_repr(obji)

        r = _walk(obj, 0)
        try:
            sentry_logger.debug(f'dumping {obj} -> {len(r)}')
        except:
            sentry_logger.debug(f'dumping {obj.__class__} instance -> {len(r)}')
        return r

    sentry_sdk.utils.object_to_json = object_to_json


def main() -> None:
    config_logger('adasd', level=logging.INFO)
    logger = logging.getLogger()
    logger.info('foo')


if __name__ == '__main__':
    main()
