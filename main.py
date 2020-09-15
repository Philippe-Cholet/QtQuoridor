# utf-8
import logging
import sys
from datetime import datetime
from typing import Iterator, NamedTuple, Optional, Set

from PySide2 import QtCore as qtc, QtGui as qtg, QtWidgets as qtw

# Sizes
CELL_SIZE = 50
WALL_SIZE = 20
GRID_SIZE = CELL_SIZE * 9 + WALL_SIZE * 8  # == 610
PLAYER_SIZE = 35
SizePolicyFixed = qtw.QSizePolicy(*(qtw.QSizePolicy.Fixed,) * 2)
SizePolicyExpanding = qtw.QSizePolicy(*(qtw.QSizePolicy.Expanding,) * 2)

# Colors: 'color name', 0x00ff00 or qtg.QColor(r, g, b, a)
# Commented colors are some colors I tried, I still search a better looking.
CELL_COLOR = 'orange'  # 0xa0522d
VOID_COLOR = WALL_COLOR = 'cyan'  # 0xffa54f
PLAYER_COLORS = 'green', 'red'

# Fonts
MESSAGE_FONT = qtg.QFont('Times', 13)
PLAYER_FONT = qtg.QFont('Times', 15)
TURN_FONT = qtg.QFont('Times', 20, qtg.QFont.Bold)


class Position(NamedTuple):
    row: int
    col: int

    def in_grid(self) -> bool:
        return 0 <= self.row < 9 and 0 <= self.col < 9

    def __add__(self, other):
        assert isinstance(other, Position)
        return Position(self.row + other.row, self.col + other.col)

    def __sub__(self, other):
        assert isinstance(other, Position)
        return Position(self.row - other.row, self.col - other.col)

    def __mul__(self, n):
        assert isinstance(n, int)
        return Position(self.row * n, self.col * n)

    def __floordiv__(self, n):
        assert isinstance(n, int)
        return Position(self.row // n, self.col // n)

    def manhattan(self, other: 'Position') -> int:
        return sum(map(abs, self - other))


# Moves: North, South, West, East
MOVES = Position(-1, 0), Position(1, 0), Position(0, -1), Position(0, 1)
PLAYER_STARTS = Position(8, 4), Position(0, 4)
PLAYER_HAS_WIN = (
    lambda pos: pos.row == 0,
    lambda pos: pos.row == 8,
)


class ClickableBoardWidget(qtw.QPushButton):
    def __init__(self, board: 'Board', color: str):
        super().__init__(board)
        self.setFlat(True)
        # Color
        self.setAutoFillBackground(True)
        self.changeColor(color)
        # Transfer click to the parent board.
        self.clicked.connect(lambda: board.receiveClick(self))

    def changeColor(self, color: str):
        palette = self.palette()
        palette.setColor(qtg.QPalette.Button, qtg.QColor(color))
        self.setPalette(palette)


class UnclickableBoardWidget(qtw.QWidget):
    def __init__(self, board: 'Board', color: str):
        super().__init__(board)
        self.setAutoFillBackground(True)
        self.changeColor(color)

    def changeColor(self, color: str):
        palette = self.palette()
        palette.setColor(qtg.QPalette.Window, qtg.QColor(color))
        self.setPalette(palette)


class Cell(ClickableBoardWidget):
    def __init__(self, board: 'Board'):
        super().__init__(board, CELL_COLOR)
        self.setSizePolicy(SizePolicyFixed)

    def sizeHint(self):
        return qtc.QSize(CELL_SIZE, CELL_SIZE)


class Wall(ClickableBoardWidget):
    def __init__(self, board: 'Board'):
        super().__init__(board, WALL_COLOR)
        self.setMinimumSize(WALL_SIZE, WALL_SIZE)
        self.setSizePolicy(SizePolicyExpanding)

    def filledBy(self, playerIndex: int):
        self.changeColor(PLAYER_COLORS[playerIndex])


class Void(UnclickableBoardWidget):
    def __init__(self, board: 'Board'):
        super().__init__(board, VOID_COLOR)
        self.setMinimumSize(WALL_SIZE, WALL_SIZE)
        self.setSizePolicy(SizePolicyExpanding)

    def filledBy(self, playerIndex: int):
        self.changeColor(PLAYER_COLORS[playerIndex])


class PlayerWidget(UnclickableBoardWidget):
    def __init__(self, board: 'Board', color: str):
        super().__init__(board, color)
        self.setSizePolicy(SizePolicyFixed)

    def sizeHint(self):
        return qtc.QSize(PLAYER_SIZE, PLAYER_SIZE)


class Game:
    ERROR_BLOCK_HIM = 'You can not entirely block another player.'
    ERROR_BLOCK_YOU = 'You can not entirely block yourself.'
    ERROR_FAR_AWAY = 'You can not go that far.'
    ERROR_GHOST = 'You can not go through a wall.'
    ERROR_JUMP = 'To jump %s an enemy, you need %%s.'
    ERROR_NO_WALL = 'You can not put up a wall you do not have.'
    ERROR_NOTHING = 'You must move or add a wall (if you have).'
    ERROR_WALL_INTERSECTION = 'You can not create a wall twice.'

    def __init__(self):
        self.nb_players = 2
        self.players_positions = list(PLAYER_STARTS)
        self.wall_parts: Set[Position] = set()
        self.index = 0
        self.count_walls = [20 // self.nb_players] * self.nb_players

    def has_win(self, index: int = None, position: Position = None) -> bool:
        if index is None:
            index = self.index
        if position is None:
            position = self.players_positions[index]
        return PLAYER_HAS_WIN[index](position)

    def next_turn(self):
        if not self.has_win():
            self.index = (self.index + 1) % self.nb_players

    def naive_neighbors(
        self, position: Position = None, wall_parts: Set[Position] = None,
    ) -> Iterator[Position]:
        if position is None:
            position = self.players_positions[self.index]
        if wall_parts is None:
            wall_parts = self.wall_parts
        for move in MOVES:
            neighbor = position + move
            if neighbor.in_grid() and position + neighbor not in wall_parts:
                # In the grid and no wall blocks the way.
                yield neighbor

    def can_exit(self, index: int, wall_parts: Set[Position]) -> bool:
        player_position = self.players_positions[index]
        # Simple DFS from player position to available exits.
        stack, visited = [player_position], set()
        while stack:
            position = stack.pop()
            if position not in visited:
                visited.add(position)
                for neighbor in self.naive_neighbors(position, wall_parts):
                    if self.has_win(index, neighbor):
                        return True
                    if neighbor not in visited:
                        stack.append(neighbor)
        return False

    def add_wall(self, position: Position, hv: str) -> Optional[str]:
        assert position.in_grid() and hv in ('h', 'v')
        if not self.count_walls[self.index]:
            return self.ERROR_NO_WALL
        x = -1 if hv == 'v' else 1
        move, other_move = (Position(0, 1), Position(1, 0))[::x]
        wall_parts = {position * 2 + other_move + move * n for n in range(3)}
        logging.info(
            f'New wall parts at {position}, {hv}: '
            + ', '.join(map(str, sorted(wall_parts)))
        )
        if wall_parts & self.wall_parts:
            return self.ERROR_WALL_INTERSECTION
        wall_parts |= self.wall_parts
        for index in range(self.nb_players):
            if not self.can_exit(index, wall_parts):
                if index == self.index:
                    return self.ERROR_BLOCK_YOU
                return self.ERROR_BLOCK_HIM
        # Wall parts accepted, update data.
        self.wall_parts |= wall_parts
        self.count_walls[self.index] -= 1
        self.next_turn()

    # Quite long if an error is raised, it provides an useful error message.
    def move_to(self, destination: Position) -> Optional[str]:
        assert destination.in_grid()
        current_position = self.players_positions[self.index]
        distance = current_position.manhattan(destination)
        if not distance:
            return self.ERROR_NOTHING
        if distance > 2:
            return self.ERROR_FAR_AWAY
        if distance == 1:
            if destination not in self.naive_neighbors():
                return self.ERROR_GHOST
        if distance == 2:
            # Keep the eventuality of four players someday.
            diff = destination - current_position
            assert diff in {(-2, 0), (0, -2), (0, 2), (2, 0),
                            (-1, -1), (-1, 1), (1, -1), (1, 1)}
            if 0 in diff:
                msg = self.ERROR_JUMP % 'over'
                enemy = current_position + diff // 2
                if enemy not in self.players_positions:
                    return self.ERROR_FAR_AWAY
                if enemy not in self.naive_neighbors():
                    return msg % 'no wall\nbetween you and him/her'
                if destination not in self.naive_neighbors(enemy):
                    return msg % 'no wall behind him/her'
            else:
                msg = self.ERROR_JUMP % 'beside'
                enemies = [
                    enemy
                    for enemy in self.players_positions
                    if current_position.manhattan(enemy) == 1
                ]
                if not enemies:
                    return self.ERROR_FAR_AWAY
                enemies = [
                    enemy
                    for enemy in enemies
                    if enemy.manhattan(destination) == 1
                ]
                if not enemies:
                    return self.ERROR_FAR_AWAY
                close = set(self.naive_neighbors())
                enemies = [enemy for enemy in enemies if enemy in close]
                if not enemies:
                    return msg % 'no wall\nbetween you and him/her'
                behinds = [
                    (enemy, current_position + (enemy - current_position) * 2)
                    for enemy in enemies
                ]
                enemies = [
                    enemy
                    for enemy, behind in behinds
                    if not behind.in_grid()
                    or behind not in self.naive_neighbors(enemy)
                ]
                if not enemies:
                    return msg % 'a wall behind him/her'
                enemies = [
                    enemy
                    for enemy in enemies
                    if destination in self.naive_neighbors(enemy)
                ]
                if not enemies:
                    return msg % 'no wall\nbetween him/her and the destination'
        self.players_positions[self.index] = destination
        self.next_turn()


class Board(qtw.QWidget):
    def __init__(self, labels):
        assert len(labels) in (4, 6)
        super().__init__()
        self.turnLabel, *self.playerLabels, self.messageLabel = labels
        self.isFinished = False
        # Layout
        layout = qtw.QGridLayout()
        layout.setSpacing(0)
        # Cell/Wall/Void widgets (in the layout)
        self.posToWidget = {}
        for widget, position in self._generateBoardWidgets():
            layout.addWidget(widget, *position)
            self.posToWidget[position] = widget
        # Players widgets (in the layout)
        self.players = ()  # Not meant to be changed once it is fully defined.
        for color, (i, j) in zip(PLAYER_COLORS, PLAYER_STARTS):
            player = PlayerWidget(self, color)
            layout.addWidget(player, 2 * i, 2 * j, qtc.Qt.AlignCenter)
            self.players += (player,)
        self.playerIndex = 0
        self.setLayout(layout)
        # Size
        self.setSizePolicy(SizePolicyFixed)
        # Game validator
        self.game = Game()

    def _generateBoardWidgets(self):
        # 18 == 2 * 9, 16 == 2 * (9 - 1), 9 being the grid size.
        for row in range(0, 18, 2):
            for col in range(0, 18, 2):
                if row and col:
                    yield Void(self), Position(row - 1, col - 1)
                if row:
                    cls = Wall if col < 16 else Void
                    yield cls(self), Position(row - 1, col)
                if col:
                    cls = Wall if row < 16 else Void
                    yield cls(self), Position(row, col - 1)
                yield Cell(self), Position(row, col)

    def sizeHint(self):
        return qtc.QSize(GRID_SIZE, GRID_SIZE)

    def movePlayer(self, position: Position):
        layout = self.layout()
        player = self.players[self.playerIndex]
        layout.takeAt(layout.indexOf(player))

        # BUG: A player sometimes disappear behind the cell it is over
        # when the mouse come over the cell. The cell seems to be repainted,
        # ignoring the player that should be keeped over it. It seems to be
        # only momentarily (but still annoying) thanks to what's below.
        # Note that it happens only when it is the turn of the other player.
        cell = self.posToWidget[position]
        # layout.takeAt(layout.indexOf(cell))
        # layout.addWidget(cell, *position)
        player.setParent(cell)

        layout.addWidget(player, *position, alignment=qtc.Qt.AlignCenter)

    def addWall(self, position: Position, vertical: bool):
        move = Position(vertical, not vertical)
        positions = [position + move * n for n in range(3)]
        for pos in positions:
            assert isinstance(self.posToWidget[pos], (Wall, Void))
            self.posToWidget[pos].filledBy(self.playerIndex)
        self.playerLabels[self.playerIndex].addWall()

    def nextTurn(self):
        if self.game.has_win():
            self.isFinished = True
            self.turnLabel.showWinner()  # To display who won.
        else:
            self.playerIndex = (self.playerIndex + 1) % len(self.players)
            self.turnLabel.nextTurn()  # To display whose turn it is.

    @qtc.Slot()
    def receiveClick(self, clickedObject: ClickableBoardWidget) -> None:
        assert isinstance(clickedObject, (Cell, Wall))
        if self.isFinished:
            self.messageLabel.setText('It is over!')
            return
        layout = self.layout()
        row, col, *_ = layout.getItemPosition(layout.indexOf(clickedObject))
        item_position = Position(row, col)
        cell_position = item_position // 2
        logging.info(
            'Click %s at %s', clickedObject.__class__.__name__, item_position,
        )
        if isinstance(clickedObject, Cell):
            # Try to move in the game then update player widget.
            message = self.game.move_to(cell_position)
            self.messageLabel.setText(message)
            if message is not None:
                logging.error(message)
                return
            logging.info('Move accepted!')
            self.movePlayer(item_position)
        else:
            # Try to add a wall in the game then update wall/void widgets.
            vertical = col % 2
            message = self.game.add_wall(cell_position, 'hv'[vertical])
            self.messageLabel.setText(message)
            if message is not None:
                logging.error(message)
                return
            logging.info('Wall accepted!')
            self.addWall(item_position, vertical)
        # Update player turn.
        self.nextTurn()


class TurnLabel(qtw.QLabel):
    TURN_MSG = "It is Player %s's turn."
    WINNER_MSG = 'Player %s won!'

    def __init__(self, nbPlayers: int):
        super().__init__()
        self.nbPlayers = nbPlayers
        self.index = 0  # It will be between 1 and nbPlayers included.
        self.setFont(TURN_FONT)
        self.nextTurn()

    def nextTurn(self):
        # Update index, color and text, in that order.
        self.index = (self.index % self.nbPlayers) + 1

        color = PLAYER_COLORS[self.index - 1]
        palette = self.palette()
        palette.setColor(qtg.QPalette.WindowText, qtg.QColor(color))
        self.setPalette(palette)

        self.setText(self.TURN_MSG % self.index)

    def showWinner(self):
        # The current color is already the good one.
        self.setText(self.WINNER_MSG % self.index)


class PlayerLabel(qtw.QLabel):
    def __init__(self, playerIndex: int, nbPlayers: int):
        super().__init__()
        self.nbWalls = 20 // nbPlayers
        self._text = 'Player %s: %%s wall%%s' % playerIndex

        self.setFont(PLAYER_FONT)

        color = PLAYER_COLORS[playerIndex - 1]
        palette = self.palette()
        palette.setColor(qtg.QPalette.WindowText, qtg.QColor(color))
        self.setPalette(palette)

        self.writeText()

    def writeText(self):
        text = self._text % (self.nbWalls or "no", 's' * (self.nbWalls > 1))
        self.setText(text)

    def addWall(self):
        self.nbWalls -= 1
        self.writeText()


class MainWindow(qtw.QMainWindow):
    def __init__(self):
        super().__init__()
        self.nbPlayers = 2
        self.setWindowTitle('My Quoridor App')

        # TODO: Create an icon.
        # self.setWindowIcon(qtg.QIcon('icon.ico'))

        # Toolbar
        self.toolbar = self.addToolBar('My toolbar')
        self.toolbar.setMovable(False)
        # To keep it visible even if the user tries to hide it.
        # self.toolbar.visibilityChanged.connect(
        #     lambda: self.toolbar.isVisible() or self.toolbar.setVisible(True)
        # )
        # Or a better way...

        # New game
        new_game_action = qtw.QAction('New game', self)
        new_game_action.setToolTip('Start a new game.')
        new_game_action.setShortcut('Ctrl+n')
        new_game_action.triggered.connect(self.newGame)
        self.toolbar.addAction(new_game_action)

        # Screenshot
        screenshot_action = qtw.QAction('Screenshot', self)
        screenshot_action.setToolTip('Take a screenshot of the game board.')
        screenshot_action.setShortcut('Ctrl+p')
        screenshot_action.triggered.connect(self.screenshot)
        self.toolbar.addAction(screenshot_action)

        # Quit without saving, unless I change my mind later.
        quit_action = qtw.QAction('Quit', self)
        quit_action.setToolTip('Quit without saving.')
        quit_action.setShortcut('Ctrl+q')
        quit_action.triggered.connect(self.close)
        self.toolbar.addAction(quit_action)

        # TODO: Add actions: "Open" a previous game & "Save" the game.

        self.defineCentralWidget()

    def defineCentralWidget(self):
        # Right Panel: [[Turn], [Player1], [Player2], [Message]]
        labels = [TurnLabel(self.nbPlayers)]
        labels.extend(
            PlayerLabel(index, self.nbPlayers)
            for index in range(1, self.nbPlayers + 1)
        )
        labels.append(qtw.QLabel('Error messages will be displayed here.'))
        labels[-1].setFont(MESSAGE_FONT)

        rightLayout = qtw.QVBoxLayout()
        for label in labels:
            rightLayout.addWidget(label, alignment=qtc.Qt.AlignCenter)
        # Layout: [Board, Right Panel]
        mainLayout = qtw.QHBoxLayout()
        # Board have a direct access to labels in the right panel.
        mainLayout.addWidget(Board(labels))
        rightPanel = qtw.QWidget()
        rightPanel.setLayout(rightLayout)
        mainLayout.addWidget(rightPanel)
        # Put it in a central widget
        widget = qtw.QWidget()
        widget.setLayout(mainLayout)
        self.setCentralWidget(widget)

    def newGame(self):
        self.centralWidget().destroy()
        self.defineCentralWidget()

    def screenshot(self):
        filepath, _ = qtw.QFileDialog.getSaveFileName(
            dir=datetime.now().strftime('Quoridor %Y-%m-%d %H-%M-%S'),
            filter='Images (*.png *.jpg)',
        )
        if filepath:
            fileformat = filepath.rsplit('.', maxsplit=1)[-1]  # 'png' or 'jpg'
            self.centralWidget().grab().save(filepath, fileformat)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = qtw.QApplication([])

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
