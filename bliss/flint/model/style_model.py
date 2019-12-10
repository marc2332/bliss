class Style:
    def __init__(
        self,
        lineStyle: str = None,
        lineColor: Tuple[int, int, int] = None,
        linePalette: int = None,
        symbolStyle: str = None,
        symbolSize: float = None,
        symbolColor: Tuple[int, int, int] = None,
        colormapLut: str = None,
        fillStyle: str = None,
    ):
        super(Style, self).__init__()
        self.__lineStyle = lineStyle
        self.__lineColor = lineColor
        self.__linePalette = linePalette
        self.__symbolStyle = symbolStyle
        self.__symbolSize = symbolSize
        self.__symbolColor = symbolColor
        self.__colormapLut = colormapLut
        self.__fillStyle = fillStyle

    @property
    def lineStyle(self):
        return self.__lineStyle

    @property
    def lineColor(self):
        return self.__lineColor

    @property
    def linePalette(self):
        return self.__linePalette

    @property
    def fillStyle(self):
        return self.__fillStyle

    @property
    def symbolStyle(self):
        return self.__symbolStyle

    @property
    def symbolSize(self):
        return self.__symbolSize

    @property
    def symbolColor(self):
        return self.__symbolColor

    @property
    def colormapLut(self):
        return self.__colormapLut
