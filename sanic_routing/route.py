import typing as t
from collections import defaultdict, namedtuple

from sanic.exceptions import InvalidUsage

from .exceptions import RouteExists
from .patterns import REGEX_TYPES
from .utils import parts_to_path

ParamInfo = namedtuple(
    "ParamInfo", ("name", "raw_path", "label", "cast", "pattern")
)


class Route:
    def __init__(self, router, raw_path, name, requirements):
        self.router = router
        self.name = name
        self.requirements = requirements
        self.handlers = defaultdict(dict)
        self._params = defaultdict(list)
        self.raw_paths = set()

        parts = tuple(raw_path.split(self.router.delimiter))
        self.path = parts_to_path(parts)
        self.parts = tuple(self.path.split(self.router.delimiter))
        self.static = "<" not in self.path

    def __repr__(self):
        display = (
            f"{self.name}|{self.path}"
            if self.name and self.name != self.path
            else self.path
        )
        return f"<Route: {display}>"

    # def __call__(self, raw_path, method="base", **kwargs):
    #     try:
    #         return self.handlers[raw_path][method](**kwargs)
    #     except KeyError:
    #         raise self.router.method_handler_exception(
    #             f"Method '{method}' not found on {self}"
    #         )

    def get_handler(self, raw_path, method, **kwargs):
        method = method or self.router.DEFAULT_METHOD
        raw_path = raw_path.lstrip("/")
        try:
            return self.handlers[raw_path][method]
        except KeyError:
            raise self.router.method_handler_exception(
                f"Method '{method}' not found on {self}"
            )

    def add_handler(self, raw_path, handler, method):
        if self.static and self.handlers:
            raise RouteExists(
                f"Route already registered: {raw_path} [{method}]"
            )

        if method in self.handlers.get(raw_path, {}):
            raise RouteExists(
                f"Route already registered: {raw_path} [{method}]"
            )
        self.handlers[raw_path][method.upper()] = handler

        if not self.static:
            parts = tuple(raw_path.split(self.router.delimiter))
            for idx, part in enumerate(parts):
                if "<" in part:
                    if ":" in part:
                        (
                            name,
                            label,
                            _type,
                            pattern,
                        ) = self.parse_parameter_string(part[1:-1])
                        self.add_parameter(
                            idx, name, raw_path, label, _type, pattern
                        )
                    else:
                        self.add_parameter(
                            idx, part[1:-1], raw_path, "string", str, None
                        )

    def add_parameter(
        self,
        idx: int,
        name: str,
        raw_path: str,
        label: str,
        cast: t.Type,
        pattern=None,
    ):
        if label in self._params[idx]:
            raise RouteExists(f"{self} already has parameter defined at {idx}")

        self._params[idx].append(
            ParamInfo(name, raw_path, label, cast, pattern)
        )

    def finalize_params(self):
        self.params = {
            k: sorted(v, key=self._sorting, reverse=True)
            for k, v in self._params.items()
        }

    @staticmethod
    def _sorting(item) -> int:
        try:
            return list(REGEX_TYPES.keys()).index(item.label)
        except ValueError:
            raise InvalidUsage(f"Unknown path type: {item.label}")

    @staticmethod
    def parse_parameter_string(parameter_string: str):
        """Parse a parameter string into its constituent name, type, and
        pattern

        For example::

            parse_parameter_string('<param_one:[A-z]>')` ->
                ('param_one', '[A-z]', <class 'str'>, '[A-z]')

        :param parameter_string: String to parse
        :return: tuple containing
            (parameter_name, parameter_type, parameter_pattern)
        """
        # We could receive NAME or NAME:PATTERN
        name = parameter_string
        label = "string"
        if ":" in parameter_string:
            name, label = parameter_string.split(":", 1)
            if not name:
                raise ValueError(
                    f"Invalid parameter syntax: {parameter_string}"
                )

        default = (str, label)
        # Pull from pre-configured types
        _type, pattern = REGEX_TYPES.get(label, default)
        return name, label, _type, pattern