from unittest import TestCase
from rx.testing import TestScheduler, ReactiveTest
from rx import subject
from operators import rate_limit, assembly_until_eol, ordered_resolution

on_next = ReactiveTest.on_next
on_completed = ReactiveTest.on_completed
on_error = ReactiveTest.on_error
subscribe = ReactiveTest.subscribe
subscribed = ReactiveTest.subscribed
disposed = ReactiveTest.disposed
created = ReactiveTest.created


class Test(TestCase):
    def test_assembly_until_eol(self):
        scheduler = TestScheduler()
        xs = scheduler.create_hot_observable(
            on_next(201, 'full command\r\n'),
            on_next(202, 'partial1'),
            on_next(203, 'partial2\r\n'),
            on_next(204, 'new command\r\n'),
            on_next(205, 'multiple command\r\nin one place\r\n'),
        )
        def create():
            return xs.pipe(
                assembly_until_eol()
            )

        res = scheduler.start(create=create)
        assert res.messages == [
            on_next(201, 'full command'),
            on_next(203, 'partial1partial2'),
            on_next(204, 'new command'),
            on_next(205, 'multiple command'),
            on_next(205, 'in one place'),
        ]

    def test_rate_limit(self):
        scheduler = TestScheduler()
        xs = scheduler.create_hot_observable(
            on_next(201, 1),
            on_next(205, 5),
            on_next(206, 6),
            on_next(208, 8),
        )

        def create():
            return xs.pipe(
                rate_limit(2.0)
            )

        res = scheduler.start(create=create)

        assert res.messages == [
            on_next(201, 1),
            on_next(205, 5),
            on_next(207, 6),
            on_next(209, 8),
        ]

    def test_ordered_resolve(self):
        observable = subject.Subject()
        piped = observable.pipe(
            ordered_resolution()
        )

        piped.subscribe(
            lambda v: print(f"1: {v}"),
            lambda err: print(f"1: {err}"),
            lambda: print("1 complete.")
        )

        piped.subscribe(
            lambda v: print(f"2: {v}"),
            lambda err: print(f"2: {err}"),
            lambda: print("2 complete.")
        )

        observable.on_next(1)
        observable.on_next(2)



