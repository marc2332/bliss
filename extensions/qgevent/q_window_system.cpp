#include "q_window_system.h"
//#include <QtGui/qpa/qwindowsysteminterface.h>
#include <QtCore/qeventloop.h>

extern uint qGlobalPostedEventsCount(); // from qapplication.cpp

class QWindowSystemInterface
{
public:
  static bool sendWindowSystemEvents(QEventLoop::ProcessEventsFlags flags);
  static int windowSystemEventsQueued();
};

namespace  WindowSystemInterface
{

  int sendWindowSystemEvents(int flags)
  {
    return QWindowSystemInterface::sendWindowSystemEvents((QEventLoop::ProcessEventsFlags)flags);
  }

  int hasPendingEvents()
  {
    return qGlobalPostedEventsCount() || QWindowSystemInterface::windowSystemEventsQueued();
  }
}
