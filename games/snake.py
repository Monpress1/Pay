# games/snake.py
import random

class SnakeGame:
    def __init__(self, player1_id, player2_id, board_size=20):
        self.board_size = board_size
        self.players = {
            player1_id: {'snake': [{'x': 5, 'y': 5}], 'direction': 'right', 'alive': True, 'score': 0},
            player2_id: {'snake': [{'x': 15, 'y': 15}], 'direction': 'left', 'alive': True, 'score': 0}
        }
        self.food = self.generate_food()
        self.winner = None

    def generate_food(self):
        while True:
            food_pos = {'x': random.randint(0, self.board_size - 1), 'y': random.randint(0, self.board_size - 1)}
            is_on_snake = any(food_pos in player['snake'] for player in self.players.values())
            if not is_on_snake:
                return food_pos

    def update_direction(self, player_id, new_direction):
        current_dir = self.players[player_id]['direction']
        if (new_direction == 'up' and current_dir != 'down') or \
           (new_direction == 'down' and current_dir != 'up') or \
           (new_direction == 'left' and current_dir != 'right') or \
           (new_direction == 'right' and current_dir != 'left'):
            self.players[player_id]['direction'] = new_direction

    def get_state(self):
        # Update snake positions and check for collisions
        for player_id, data in self.players.items():
            if not data['alive']:
                continue
            
            head = data['snake'][0].copy()
            
            if data['direction'] == 'up':
                head['y'] -= 1
            elif data['direction'] == 'down':
                head['y'] += 1
            elif data['direction'] == 'left':
                head['x'] -= 1
            elif data['direction'] == 'right':
                head['x'] += 1
            
            # Collision with walls
            if head['x'] < 0 or head['x'] >= self.board_size or \
               head['y'] < 0 or head['y'] >= self.board_size:
                data['alive'] = False
                continue

            # Collision with self
            if head in data['snake']:
                data['alive'] = False
                continue
                
            # Collision with other snake
            other_player_id = [p_id for p_id in self.players if p_id != player_id][0]
            if head in self.players[other_player_id]['snake']:
                data['alive'] = False
                
            data['snake'].insert(0, head)
            
            # Check for food
            if head == self.food:
                data['score'] += 1
                self.food = self.generate_food()
            else:
                data['snake'].pop()

        # Check for game end
        alive_players = [p_id for p_id, data in self.players.items() if data['alive']]
        if len(alive_players) <= 1:
            if len(alive_players) == 1:
                self.winner = alive_players[0]
            else:
                self.winner = 'draw'

        return {
            "players": {p_id: {"snake": p_data['snake'], "score": p_data['score'], "alive": p_data['alive']} for p_id, p_data in self.players.items()},
            "food": self.food,
            "winner": self.winner,
            "board_size": self.board_size
        }
