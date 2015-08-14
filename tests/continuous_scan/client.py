import sys
import os
import gevent

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

from bliss.common.data_manager import get_node

toto = get_node("toto")

for node in toto.iterator().walk(filter=('scan','lima')):
  print node.db_name()

"""
for node in toto.iterator().walk(filter='lima'):
  gevent.spawn(analyse_data, node)

def analyse_data(node):
  for data in node.iterator().walk_data():
      print data
"""


