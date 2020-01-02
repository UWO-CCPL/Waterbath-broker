import argparse
import logging

import rx
import serial
from rx import subject, operators, scheduler, Observable
from rx.core.typing import Scheduler

from operators import rate_limit, ordered_resolution

logger = logging.getLogger("fp50")


class FP50Control:
    def __init__(self, serial_port, baud_rate, command_interval=0.25, terminator='\r\n'):
        self.terminator = terminator
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.command_interval = command_interval

        self.command_queue = subject.Subject()
        self.command_queue.pipe(
            rate_limit(command_interval)
        ).subscribe(self._send_command, self._error_handler)

        self.resolve_queue = subject.Subject()

        self.serial = serial.Serial(serial_port, baud_rate, xonxoff=True)  # software flow control
        self._configure_serial_receive()

    def _configure_serial_receive(self):
        def _serial_recv(sc: Scheduler, state):
            if self.serial.isOpen():
                line = self.serial.read_until(bytes(self.terminator, 'ascii')).decode('ascii')
                line.strip(self.terminator)
                self.resolve_queue.on_next(line)
                sc.schedule(_serial_recv)

        s = scheduler.NewThreadScheduler()
        s.schedule(_serial_recv)

    def _send_command(self, command: str):
        if not self.serial.isOpen():
            logger.error("Serial port is not opened. Could not send message")
            return

        logger.debug(f"Serial write: {command.encode('string_escape')}")
        self.serial.write(command)

    def _error_handler(self, error: Exception):
        logger.error(error)

    def startup(self):
        self.serial.open()
        self.command_queue.on_next("OUT_MODE_05 1\r")  # turn on unit
        self.command_queue.on_next("OUT_MODE_08 1\r")  # faster standard mode
        self.command_queue.on_next("OUT_MODE_02 0\r")  # self tuning off

    def set_temperature(self, set_point: float):
        self.command_queue.on_next(f"OUT_SP_00 {set_point:.2f}\r")

    def set_pid(self, p=None, i=None, d=None):
        if p is not None:
            self.command_queue.on_next(f"OUT_SP_6 {p:3.1f}\r")
        if i is not None:
            self.command_queue.on_next(f"OUT_SP_7 {i:3.1f}\r")
        if d is not None:
            self.command_queue.on_next(f"OUT_SP_8 {d:3.1f}\r")

    def get_power(self) -> Observable:
        """
        Upon subscription, use side effect to send a query command, and then register the resolver to read value
        :return:
        """
        return rx.from_callable(lambda: self.command_queue.on_next("IN_PV_01\r")).pipe(
            operators.flat_map(
                lambda x: self.resolve_queue.pipe(
                    ordered_resolution()
                )
            )
        )

    def get_internal_temperature(self) -> Observable:
        """
        Upon subscription, use side effect to send a query command, and then register the resolver to read value
        :return:
        """
        return rx.from_callable(lambda: self.command_queue.on_next("IN_PV_00\r")).pipe(
            operators.flat_map(
                lambda x: self.resolve_queue.pipe(
                    ordered_resolution()
                )
            )
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM2")
    parser.add_argument("--baud", default=9600, type=int)

    subparsers = parser.add_subparsers(required=True, dest="command")
    setpoint_parser = subparsers.add_parser("setpoint")
    setpoint_parser.add_argument("temperature", type=float)

    pid_parser = subparsers.add_parser("pid")
    pid_parser.add_argument("--p", type=float, default=None)
    pid_parser.add_argument("--i", type=float, default=None)
    pid_parser.add_argument("--d", type=float, default=None)

    temp_parser = subparsers.add_parser("get_temp")
    power_parser = subparsers.add_parser("get_power")

    args = parser.parse_args()

    fp50 = FP50Control(args.port, args.baud)
    if args.command == "setpoint":
        fp50.set_temperature(args.temperature)
        print(f"Set temperature to {args.temperature}")
    elif args.command == "pid":
        fp50.set_pid(args.p, args.i, args.d)
        print(f"Set PID: P={args.p} I={args.i} D={args.d}")
    elif args.command == "get_temp":
        fp50.get_internal_temperature().subscribe(
            lambda x: print(f"Internal temperature: {x}")
        )
    elif args.command == "get_power":
        fp50.get_power().subscribe(
            lambda x: print(f"Power: {x}")
        )
    else:
        print(f"Unknown command {args.command}")
