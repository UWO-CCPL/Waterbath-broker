import rx.scheduler.scheduler
import datetime
from rx import disposable


def assembly_until_eol(eol='\r\n'):
    buffer = ''

    def _assembly_until_eol(source):
        def subscribe(observer, scheduler: rx.scheduler.scheduler.Scheduler):
            def on_next(value: str):
                nonlocal buffer
                while True:
                    # there might be more than one eol in one value.
                    index = value.find(eol)
                    if index == -1:
                        # no eol
                        buffer += value
                        break
                    else:
                        # has eol
                        buffer += value[:index]
                        observer.on_next(buffer)
                        value = value[index + len(eol):] or ''
                        buffer = ''

            return source.subscribe(
                on_next,
                observer.on_error,
                observer.on_completed,
                scheduler
            )

        return rx.create(subscribe)

    return _assembly_until_eol


def rate_limit(interval: float):
    last_event_time: datetime.datetime = datetime.datetime(1970, 1, 1)

    def _rate_limit(source):
        def subscribe(observer, scheduler: rx.scheduler.scheduler.Scheduler):
            delta = datetime.timedelta(seconds=interval)

            def on_next(value):
                nonlocal last_event_time, scheduler
                scheduler = scheduler or rx.scheduler.NewThreadScheduler()
                now = scheduler.now
                if now - last_event_time >= delta:
                    scheduler.schedule(lambda *args: observer.on_next(value))
                    last_event_time = now
                else:
                    scheduler.schedule_absolute(last_event_time + delta, lambda *args: observer.on_next(value))
                    last_event_time += delta

            return source.subscribe(
                on_next,
                observer.on_error,
                observer.on_completed,
                scheduler
            )

        return rx.create(subscribe)

    return _rate_limit


def ordered_resolution():
    observers = []

    def _ordered_resolution(source):
        def resolve(value):
            if not len(observers):
                return

            observers[0].on_next(value)
            observers[0].on_completed()

        subscription = source.subscribe(resolve)

        def subscribe(observer, scheduler=None):
            observers.append(observer)
            return disposable.Disposable(lambda: observers.remove(observer))

        return rx.create(subscribe)

    return _ordered_resolution
