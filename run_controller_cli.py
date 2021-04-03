#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os
import keyboard
import time
import shelve
import board

from aioconsole import ainput

from joycontrol import logging_default as log, utils
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState, button_push, StickState
from joycontrol.memory import FlashMemory
from joycontrol.protocol import controller_protocol_factory
from joycontrol.server import create_hid_server

logger = logging.getLogger(__name__)

"""Emulates Switch controller. Opens joycontrol.command_line_interface to send button commands and more.

While running the cli, call "help" for an explanation of available commands.

Usage:
    run_controller_cli.py <controller> [--device_id | -d  <bluetooth_adapter_id>]
                                       [--spi_flash <spi_flash_memory_file>]
                                       [--reconnect_bt_addr | -r <console_bluetooth_address>]
                                       [--log | -l <communication_log_file>]
                                       [--nfc <nfc_data_file>]
    run_controller_cli.py -h | --help

Arguments:
    controller      Choose which controller to emulate. Either "JOYCON_R", "JOYCON_L" or "PRO_CONTROLLER"

Options:
    -d --device_id <bluetooth_adapter_id>   ID of the bluetooth adapter. Integer matching the digit in the hci* notation
                                            (e.g. hci0, hci1, ...) or Bluetooth mac address of the adapter in string
                                            notation (e.g. "FF:FF:FF:FF:FF:FF").
                                            Note: Selection of adapters may not work if the bluez "input" plugin is
                                            enabled.

    --spi_flash <spi_flash_memory_file>     Memory dump of a real Switch controller. Required for joystick emulation.
                                            Allows displaying of JoyCon colors.
                                            Memory dumps can be created using the dump_spi_flash.py script.

    -r --reconnect_bt_addr <console_bluetooth_address>  Previously connected Switch console Bluetooth address in string
                                                        notation (e.g. "FF:FF:FF:FF:FF:FF") for reconnection.
                                                        Does not require the "Change Grip/Order" menu to be opened,

    -l --log <communication_log_file>       Write hid communication (input reports and output reports) to a file.

    --nfc <nfc_data_file>                   Sets the nfc data of the controller to a given nfc dump upon initial
                                            connection.
"""


def keyToConBtn(
        key):  # this method translates recorded key events to respective controller buttons pressed for recording playback
    namedKey = None
    keyBinding = {'q': 'left', 'w': 'lStickUp', 'e': 'up', 'r': 'zl', 't': 'l', 'y': 'r', 'u': 'zr', 'i': 'rStickUp',
                  'a': 'lStickL', 's': 'lStickDown', 'd': 'lStickR', 'f': 'right', 'g': 'capture', 'h': 'home',
                  'j': 'rStickL', 'k': 'rStickDown', 'l': 'rStickR', 'c': 'down', 'up': 'x', 'down': 'b', 'left': 'y',
                  'right': 'a', '-': 'minus', '+': 'plus'}
    testKeys = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'c', 'up', 'down',
                'left', 'right', '+', '-']
    for testKey in testKeys:
        testKeyCode = keyboard.key_to_scan_codes(testKey)
        # print('testKeyCode:')
        # print(testKeyCode)
        if testKeyCode[0] == key:
            namedKey = testKey
            # print('namedKey:')
            # print(namedKey)
    if namedKey in keyBinding:
        conBtnPressed = keyBinding[namedKey]
        return conBtnPressed


def bindKeyboard(
        controller_state: ControllerState):  # this method binds specific keys to each button on the pro controller for keyboard control
    # callbacks:
    def APress(self):
        controller_state.button_state.set_button('a')

    def AUnpress(self):
        controller_state.button_state.set_button('a', pushed=False)

    def BPress(self):
        controller_state.button_state.set_button('b')

    def BUnpress(self):
        controller_state.button_state.set_button('b', pushed=False)

    def XPress(self):
        controller_state.button_state.set_button('x')

    def XUnpress(self):
        controller_state.button_state.set_button('x', pushed=False)

    def YPress(self):
        controller_state.button_state.set_button('y')

    def YUnpress(self):
        controller_state.button_state.set_button('y', pushed=False)

    def UPPress(self):
        controller_state.button_state.set_button('up')

    def UPUnpress(self):
        controller_state.button_state.set_button('up', pushed=False)

    def DOWNPress(self):
        controller_state.button_state.set_button('down')

    def DOWNUnpress(self):
        controller_state.button_state.set_button('down', pushed=False)

    def LEFTPress(self):
        controller_state.button_state.set_button('left')

    def LEFTUnpress(self):
        controller_state.button_state.set_button('left', pushed=False)

    def RIGHTPress(self):
        controller_state.button_state.set_button('right')

    def RIGHTUnpress(self):
        controller_state.button_state.set_button('right', pushed=False)

    def PLUSPress(self):
        controller_state.button_state.set_button('plus')

    def PLUSUnpress(self):
        controller_state.button_state.set_button('plus', pushed=False)

    def MINUSPress(self):
        controller_state.button_state.set_button('minus')

    def MINUSUnpress(self):
        controller_state.button_state.set_button('minus', pushed=False)

    def HOMEPress(self):
        controller_state.button_state.set_button('home')

    def HOMEUnpress(self):
        controller_state.button_state.set_button('home', pushed=False)

    def CAPPress(self):
        controller_state.button_state.set_button('capture')

    def CAPUnpress(self):
        controller_state.button_state.set_button('capture', pushed=False)

    def LBUMPPress(self):
        controller_state.button_state.set_button('l')

    def LBUMPUnpress(self):
        controller_state.button_state.set_button('l', pushed=False)

    def RBUMPPress(self):
        controller_state.button_state.set_button('r')

    def RBUMPUnpress(self):
        controller_state.button_state.set_button('r', pushed=False)

    def ZLPress(self):
        controller_state.button_state.set_button('zl')

    def ZLUnpress(self):
        controller_state.button_state.set_button('zl', pushed=False)

    def ZRPress(self):
        controller_state.button_state.set_button('zr')

    def ZRUnpress(self):
        controller_state.button_state.set_button('zr', pushed=False)

        # Stick state handler callbacks

    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state

    def UpLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'up', None)

    def DownLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'down', None)

    def LeftLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'left', None)

    def RightLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'right', None)

    def LStickUnpress(self):
        ControllerCLI._set_stick(LeftStick, 'center', None)

        # Right Stick

    def UpRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'up', None)

    def DownRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'down', None)

    def LeftRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'left', None)

    def RightRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'right', None)

    def RStickUnpress(self):
        ControllerCLI._set_stick(RightStick, 'center', None)

    # key listeners
    keyboard.on_press_key('q', LEFTPress)
    keyboard.on_release_key('q', LEFTUnpress)

    keyboard.on_press_key('w', UpLStickPress)
    keyboard.on_release_key('w', LStickUnpress)

    keyboard.on_press_key('e', UPPress)
    keyboard.on_release_key('e', UPUnpress)

    keyboard.on_press_key('r', ZLPress)
    keyboard.on_release_key('r', ZLUnpress)

    keyboard.on_press_key('t', LBUMPPress)
    keyboard.on_release_key('t', LBUMPUnpress)

    keyboard.on_press_key('y', RBUMPPress)
    keyboard.on_release_key('y', RBUMPUnpress)

    keyboard.on_press_key('u', ZRPress)
    keyboard.on_release_key('u', ZRUnpress)

    keyboard.on_press_key('i', UpRStickPress)
    keyboard.on_release_key('i', RStickUnpress)

    keyboard.on_press_key('a', LeftLStickPress)
    keyboard.on_release_key('a', LStickUnpress)

    keyboard.on_press_key('s', DownLStickPress)
    keyboard.on_release_key('s', LStickUnpress)

    keyboard.on_press_key('d', RightLStickPress)
    keyboard.on_release_key('d', LStickUnpress)

    keyboard.on_press_key('f', RIGHTPress)
    keyboard.on_release_key('f', RIGHTUnpress)

    keyboard.on_press_key('g', CAPPress)
    keyboard.on_release_key('g', CAPUnpress)

    keyboard.on_press_key('h', HOMEPress)
    keyboard.on_release_key('h', HOMEUnpress)

    keyboard.on_press_key('j', LeftRStickPress)
    keyboard.on_release_key('j', RStickUnpress)

    keyboard.on_press_key('k', DownRStickPress)
    keyboard.on_release_key('k', RStickUnpress)

    keyboard.on_press_key('l', RightRStickPress)
    keyboard.on_release_key('l', RStickUnpress)

    keyboard.on_press_key('c', DOWNPress)
    keyboard.on_release_key('c', DOWNUnpress)

    keyboard.on_press_key('+', PLUSPress)
    keyboard.on_release_key('+', PLUSUnpress)

    keyboard.on_press_key('-', MINUSPress)
    keyboard.on_release_key('-', MINUSUnpress)

    keyboard.on_press_key('up', XPress)
    keyboard.on_release_key('up', XUnpress)

    keyboard.on_press_key('down', BPress)
    keyboard.on_release_key('down', BUnpress)

    keyboard.on_press_key('left', YPress)
    keyboard.on_release_key('left', YUnpress)

    keyboard.on_press_key('right', APress)
    keyboard.on_release_key('right', AUnpress)
    print(' ')
    # print('keys bound')


async def directStateSet(btnTrans,
                         controller_state: ControllerState):  # this method sets button/stick states during recording playback (button PRESS/ stick UDLR)
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    btnsList = ['x', 'y', 'b', 'a', 'plus', 'minus', 'home', 'capture', 'zl', 'zr', 'l', 'r', 'up', 'down', 'left',
                'right']
    lStickList = ['lStickUp', 'lStickDown', 'lStickL', 'lStickR']
    rStickList = ['rStickUp', 'rStickDown', 'rStickL', 'rStickR']
    if btnTrans in btnsList:
        # print(btnTrans)
        controller_state.button_state.set_button(btnTrans)
        await controller_state.send()
    elif btnTrans in lStickList:
        # print(btnTrans)
        if btnTrans == 'lStickDown':
            ControllerCLI._set_stick(LeftStick, 'down', None)
            await controller_state.send()
        elif btnTrans == 'lStickUp':
            ControllerCLI._set_stick(LeftStick, 'up', None)
            await controller_state.send()
        elif btnTrans == 'lStickL':
            ControllerCLI._set_stick(LeftStick, 'left', None)
            await controller_state.send()
        elif btnTrans == 'lStickR':
            ControllerCLI._set_stick(LeftStick, 'right', None)
            await controller_state.send()
    elif btnTrans in rStickList:
        if btnTrans == 'rStickDown':
            ControllerCLI._set_stick(RightStick, 'down', None)
            await controller_state.send()
        elif btnTrans == 'rStickUp':
            ControllerCLI._set_stick(RightStick, 'up', None)
            await controller_state.send()
        elif btnTrans == 'rStickL':
            ControllerCLI._set_stick(RightStick, 'left', None)
            await controller_state.send()
        elif btnTrans == 'rStickR':
            ControllerCLI._set_stick(RightStick, 'right', None)
            await controller_state.send()


async def date_skipper(controller_state: ControllerState):
    """
    Date-Skipper
    Skip N days
    """
    number_days = 815

    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')

    # waits until controller is fully connected
    await controller_state.connect()

    # skip a day

    # navigate to settings menu
    await button_push(controller_state, 'right')
    await button_push(controller_state, 'b')
    await button_push(controller_state, 'right')
    await button_push(controller_state, 'down')
    await button_push(controller_state, 'right')
    await button_push(controller_state, 'a')

    # go all the way down
    await button_push(controller_state, 'down', sec=2.5)
    await asyncio.sleep(0.1)
    # system
    await button_push(controller_state, 'right')
    # date & time menu
    for _ in range(4):
        await button_push(controller_state, 'down')
        await asyncio.sleep(0.08)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.2)

    # date & time
    for _ in range(2):
        await button_push(controller_state, 'down')
        await asyncio.sleep(0.08)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.08)

    # increment year
    # go all the way right
    await button_push(controller_state, 'right', sec=1)

    for i in range(number_days):
        print(str(i) + "/" + str(number_days))
        for _ in range(4):
            await button_push(controller_state, 'left')
            await asyncio.sleep(0.04)
        await button_push(controller_state, 'up')
        for _ in range(4):
            await button_push(controller_state, 'right')
            await asyncio.sleep(0.04)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.08)

        if ((i + 1) % 30) == 0:
            await button_push(controller_state, 'up')
            await asyncio.sleep(0.04)
            await button_push(controller_state, 'up')
            await asyncio.sleep(0.04)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.1)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.1)
            await button_push(controller_state, 'down')
            await asyncio.sleep(0.04)
            await button_push(controller_state, 'down')
            await asyncio.sleep(0.04)

        await button_push(controller_state, 'a')
        await asyncio.sleep(0.08)


async def run_auto_host(controller_state: ControllerState):
    """
    Auto-Host Rolling
    Roll N days, host, soft reset and repeat
    """
    frames_away = 3
    # frames_away = 0 # for hardlocking

    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')

    # waits until controller is fully connected
    await controller_state.connect()

    # start at the den

    while True:
        for _ in range(frames_away):
            # start inviting
            print("start inviting")
            await button_push(controller_state, 'a')
            await button_push(controller_state, 'a')
            await asyncio.sleep(1.0)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.5)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.5)
            await button_push(controller_state, 'a')
            await asyncio.sleep(2.0)

            # date skip
            print("date skip")
            await button_push(controller_state, 'home')
            await asyncio.sleep(0.4)

            # navigate to settings menu
            print("navigate to settings menu")
            await button_push(controller_state, 'right')
            await button_push(controller_state, 'b')
            await button_push(controller_state, 'right')
            await button_push(controller_state, 'down')
            await button_push(controller_state, 'right')
            await button_push(controller_state, 'a')

            # go all the way down
            print("go all the way down")
            await button_push(controller_state, 'down', sec=2.5)
            # system
            await button_push(controller_state, 'a')
            # date & time menu
            for _ in range(4):
                await button_push(controller_state, 'down')
                await asyncio.sleep(0.08)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.1)

            # date & time
            for _ in range(3):
                await button_push(controller_state, 'down')
                await asyncio.sleep(0.08)
            await button_push(controller_state, 'a')
            await asyncio.sleep(0.08)

            # increment year
            print("increment year")

            await button_push(controller_state, 'right')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'right')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'up')
            await button_push(controller_state, 'a')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'a')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'a')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'a')
            await button_push(controller_state, 'y')
            await button_push(controller_state, 'a')

            # go back to game
            print("go back to game")
            await asyncio.sleep(0.08)
            await button_push(controller_state, 'home')
            await asyncio.sleep(1)
            await button_push(controller_state, 'a')
            await asyncio.sleep(1.5)

            # quit lobby
            print("quit lobby")
            await button_push(controller_state, 'down')
            await asyncio.sleep(0.08)
            await button_push(controller_state, 'a')
            await asyncio.sleep(1.2)
            await button_push(controller_state, 'a')
            await asyncio.sleep(4)

        # collect watts
        print("collect watts")
        await button_push(controller_state, 'a')
        await asyncio.sleep(1.0)
        await button_push(controller_state, 'b')
        await asyncio.sleep(1.0)
        await button_push(controller_state, 'b')
        await asyncio.sleep(1.6)
        await button_push(controller_state, 'b')
        await asyncio.sleep(1.0)

        # connect to internet
        print("connect to internet")
        await button_push(controller_state, 'y')
        await asyncio.sleep(1.0)
        await button_push(controller_state, 'plus')
        await asyncio.sleep(7.0)
        await button_push(controller_state, 'b')
        await asyncio.sleep(0.5)
        await button_push(controller_state, 'b')
        await asyncio.sleep(1.0)

        # start raid
        print("start raid")
        await button_push(controller_state, 'a')
        await asyncio.sleep(7)

        # enter code
        print("enter code")
        await button_push(controller_state, 'plus')
        await asyncio.sleep(1.0)
        await button_push(controller_state, 'a')  # 1
        await button_push(controller_state, 'down')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'right')
        await button_push(controller_state, 'a')  # 5
        await button_push(controller_state, 'left')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'l')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'l')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'l')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'l')
        await button_push(controller_state, 'a')  # 4
        await button_push(controller_state, 'plus')
        await asyncio.sleep(1)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.2)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.2)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.2)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.2)
        await button_push(controller_state, 'a')

        # wait for lobby to fill
        print("wait for lobby to fill")
        # await asyncio.sleep(65)  # FIXME
        await asyncio.sleep(6)
        await button_push(controller_state, 'home')
        await asyncio.sleep(1)
        await button_push(controller_state, 'up')
        await asyncio.sleep(0.5)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.1)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.1)
        for _ in range(22):
            await button_push(controller_state, 'a')
            await asyncio.sleep(1)

        await button_push(controller_state, 'home')
        await asyncio.sleep(1.5)
        await button_push(controller_state, 'home')
        await asyncio.sleep(35)
        # add friends while waiting

        # start raid
        print("start raid")
        await button_push(controller_state, 'up')
        await asyncio.sleep(0.1)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.4)
        await button_push(controller_state, 'a')
        # keep mashing in case someone hasn't readied up
        for _ in range(35):
            await button_push(controller_state, 'a')
            await asyncio.sleep(1)


        # close game
        print("close game")
        # await asyncio.sleep(15)
        await button_push(controller_state, 'home')
        await asyncio.sleep(1)
        await button_push(controller_state, 'x')
        await asyncio.sleep(0.1)
        await button_push(controller_state, 'a')
        await asyncio.sleep(4)

        # reset time
        print("reset time")

        # navigate to settings menu
        await button_push(controller_state, 'right')
        await button_push(controller_state, 'b')
        await button_push(controller_state, 'right')
        await button_push(controller_state, 'down')
        await button_push(controller_state, 'right')
        await button_push(controller_state, 'a')
        # go all the way down
        await button_push(controller_state, 'down', sec=2.5)
        await asyncio.sleep(0.1)
        # system
        await button_push(controller_state, 'right')
        # date & time menu
        for _ in range(4):
            await button_push(controller_state, 'down')
            await asyncio.sleep(0.08)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.2)

        # turn on & off sync clock
        print("turn on & off sync clock")
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.08)
        await button_push(controller_state, 'a')
        await asyncio.sleep(0.08)
        await button_push(controller_state, 'home')
        await asyncio.sleep(1.5)

        # start up game again, wait, and mash through until in front of den
        print("start up game again, wait, and mash through until in front of den")
        await button_push(controller_state, 'a')
        await asyncio.sleep(18)
        await button_push(controller_state, 'a')
        await asyncio.sleep(3.5)
        await button_push(controller_state, 'a')
        await asyncio.sleep(8)

async def friend_remover(
        controller_state: ControllerState):
    """
    Example controller script.
    Navigates to the "Test Controller Buttons" menu and presses all buttons.
    """
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')

    # waits until controller is fully connected
    await controller_state.connect()

    """
    # We assume we are in the "Change Grip/Order" menu of the switch
    await button_push(controller_state, 'home')

    # wait for the animation
    await asyncio.sleep(1)
    """
    num_friends = 50

    # Remove friends
    for i in range(num_friends):
        print(str(i)+"/"+str(num_friends))
        await button_push(controller_state, 'a')
        await asyncio.sleep(1.5)
        await button_push(controller_state, 'down')
        await button_push(controller_state, 'a')
        await asyncio.sleep(1.5)
        await button_push(controller_state, 'a')
        await asyncio.sleep(1.5)
        await button_push(controller_state, 'a')
        await asyncio.sleep(9)
        await button_push(controller_state, 'a')
        await asyncio.sleep(2)



async def set_nfc(controller_state, file_path):
    """
    Sets nfc content of the controller state to contents of the given file.
    :param controller_state: Emulated controller state
    :param file_path: Path to nfc dump file
    """
    loop = asyncio.get_event_loop()

    with open(file_path, 'rb') as nfc_file:
        content = await loop.run_in_executor(None, nfc_file.read)
        controller_state.set_nfc(content)


async def mash_button(controller_state, button, interval):
    # waits until controller is fully connected
    await controller_state.connect()

    if button not in controller_state.button_state.get_available_buttons():
        raise ValueError(f'Button {button} does not exist on {controller_state.get_controller()}')

    user_input = asyncio.ensure_future(
        ainput(prompt=f'Pressing the {button} button every {interval} seconds... Press <enter> to stop.')
    )
    # push a button repeatedly until user input
    while not user_input.done():
        await button_push(controller_state, button)
        await asyncio.sleep(float(interval))

    # await future to trigger exceptions in case something went wrong
    await user_input


async def _main(args):
    # parse the spi flash
    if args.spi_flash:
        with open(args.spi_flash, 'rb') as spi_flash_file:
            spi_flash = FlashMemory(spi_flash_file.read())
    else:
        # Create memory containing default controller stick calibration
        spi_flash = FlashMemory()

    # Get controller name to emulate from arguments
    controller = Controller.from_arg(args.controller)

    with utils.get_output(path=args.log, default=None) as capture_file:
        factory = controller_protocol_factory(controller, spi_flash=spi_flash)
        ctl_psm, itr_psm = 17, 19
        transport, protocol = await create_hid_server(factory, reconnect_bt_addr=args.reconnect_bt_addr,
                                                      ctl_psm=ctl_psm,
                                                      itr_psm=itr_psm, capture_file=capture_file,
                                                      device_id=args.device_id)

        controller_state = protocol.get_controller_state()

        # Create command line interface and add some extra commands
        cli = ControllerCLI(controller_state)

        # Wrap the script so we can pass the controller state. The doc string will be printed when calling 'help'
        async def _run_test_control():
            """
            test_control - test method that will be removed later
            """
            await test_control(controller_state)

        async def _run_keyboard_control():
            """
            keyboard - binds controls to keyboard. Keybinding:
            q=LEFT w=LstickUP e=UP r=ZL t=L y=R u=ZR i=RstickUP
            a=LstickLEFT s=LstickDOWN d=LstickRIGHT f=RIGHT g=capture h=home j=RstickLEFT k=RStickDOWN l=RstickRIGHT
            c=DOWN up=X down=B left=Y right=A
            plus= + minus= -
            """
            await keyboard_control(controller_state)

        async def _run_recording_control():
            """
            recording - binds controls to keyboard, and records input until recording stopped.
            saved recordings can be replayed using cmd >> recording_playback
            Keybinding:
            q=LEFT w=LstickUP e=UP r=ZL t=L y=R u=ZR i=RstickUP
            a=LstickLEFT s=LstickDOWN d=LstickRIGHT f=RIGHT g=capture h=home j=RstickLEFT k=RStickDOWN l=RstickRIGHT
            c=DOWN up=X down=B left=Y right=A
            plus= + minus= -
            """
            await record_keyboard(controller_state)

        async def _run_recording_playback():
            """
            playback - select a saved recording and replay it
            """
            await recording_playback(controller_state)

        async def _run_delete_recording():
            """
            delete_rec - select a saved recording and delete it
            """
            await delete_recording(controller_state)

        async def _run_test_controller_buttons():
            """
            test_buttons - Navigates to the "Test Controller Buttons" menu and presses all buttons.
            """
            await test_controller_buttons(controller_state)

        # Mash a button command
        async def call_mash_button(*args):
            """
            mash - Mash a specified button at a set interval
            Usage:
                mash <button> <interval>
            """
            if not len(args) == 2:
                raise ValueError('"mash_button" command requires a button and interval as arguments!')

            button, interval = args
            await mash_button(controller_state, button, interval)

        # Create nfc command
        async def nfc(*args):
            """
            nfc - Sets nfc content

            Usage:
                nfc <file_name>          Set controller state NFC content to file
                nfc remove               Remove NFC content from controller state
            """
            if controller_state.get_controller() == Controller.JOYCON_L:
                raise ValueError('NFC content cannot be set for JOYCON_L')
            elif not args:
                raise ValueError('"nfc" command requires file path to an nfc dump as argument!')
            elif args[0] == 'remove':
                controller_state.set_nfc(None)
                print('Removed nfc content.')
            else:
                await set_nfc(controller_state, args[0])

        async def _run_auto_host():
            await run_auto_host(controller_state)

        async def _run_date_skipper():
            await date_skipper(controller_state)

        async def _run_friend_remover():
            await friend_remover(controller_state)

        cli.add_command('test_buttons', _run_test_controller_buttons)
        cli.add_command('keyboard', _run_keyboard_control)
        cli.add_command('recording', _run_recording_control)
        cli.add_command('playback', _run_recording_playback)
        cli.add_command('delete_rec', _run_delete_recording)
        cli.add_command('mash', call_mash_button)
        # add the script from above
        cli.add_command('nfc', nfc)

        cli.add_command('skip', _run_date_skipper)
        cli.add_command('host', _run_auto_host)
        cli.add_command('remove', _run_friend_remover)

        if args.nfc is not None:
            await nfc(args.nfc)

        try:
            await cli.run()
        finally:
            logger.info('Stopping communication...')
            await transport.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    # log.configure(console_level=logging.ERROR)
    log.configure()

    parser = argparse.ArgumentParser()
    parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('-l', '--log')
    parser.add_argument('-d', '--device_id')
    parser.add_argument('--spi_flash')
    parser.add_argument('-r', '--reconnect_bt_addr', type=str, default=None,
                        help='The Switch console Bluetooth address, for reconnecting as an already paired controller')
    parser.add_argument('--nfc', type=str, default=None)
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _main(args)
    )
