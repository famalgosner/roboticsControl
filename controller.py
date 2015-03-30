#!/usr/bin/env python
import sys
from math import sqrt, log10, pi
from vrep import *
from util import *
from pid import PID

class SegwayController(object):

    def __init__(self, client):
        self.client = client

    def setup_body(self, body_name='body'):
        err, self.body = simxGetObjectHandle(self.client, body_name, simx_opmode_oneshot_wait)
        if err:
            log(self.client, 'ERROR GetObjectHandle code %d' % err)

    def setup_motors(self, left_motor_name="leftMotor", right_motor_name="rightMotor"):
        err_l, self.left_motor = simxGetObjectHandle(self.client, left_motor_name, simx_opmode_oneshot_wait)
        err_r, self.right_motor = simxGetObjectHandle(self.client, right_motor_name, simx_opmode_oneshot_wait)
        err = err_l or err_r
        if err:
            log(self.client, 'ERROR GetObjectHandle code %d' % err)
        self._send_target_velocities(0.0, 0.0, simx_opmode_oneshot_wait)

    def setup_sensors(self, gyro, height):
        # Placeholder
        pass

    def set_target_velocities(self, left_vel, right_vel):
        # Pause comms to sync the orders
        simxPauseCommunication(self.client, True)
        self._send_target_velocities(left_vel, right_vel, simx_opmode_streaming)
        # Re-enable comms to push the commands
        simxPauseCommunication(self.client, False)

    def _send_target_velocities(self, left_vel, right_vel, opmode):
        err_l = None
        err_r = None
        if left_vel is not None:
            err_l = simxSetJointTargetVelocity(self.client, self.left_motor,
                                               left_vel, opmode)
        if right_vel is not None:
            err_r = simxSetJointTargetVelocity(self.client, self.right_motor,
                                               right_vel, opmode)
        err = err_l or err_r
        if err > 1:
            log(self.client, 'ERROR SetJointTargetVelocity code %d' % err)


    def setup_control(self, balance_controller):
        self.balance_controller = balance_controller

#####  END CONDITIONS #########################################################

    def zero_velocity_condition(self, lin_vel, rot_vel):
        # Check if velocity is near zero (could cause issues on first cycle!)
        vel_tot = sqrt(reduce(lambda total, value: total + value**2,
                              lin_vel,
                              0.0))
        log(self.client, 'Total velocity: %f' % vel_tot)
        return vel_tot > 10.0 ** -5

    def body_height_condition(self, body_pos):
        x, y, z = body_pos
        return z > 0.04  # Wheel radius is 0.08m

    def simulation_run_condition(self, simulation_time, body_pos):
        if simulation_time < 100:
            return True
        else:
            x, y, z = body_pos
            # Wheel radius 0.08m, box length 0.1m
            height_condition = 0.04 < z < 0.7
            lateral_condition = abs(y) < 0.05
            drive_condition = abs(x) < 1
            #print z, height_condition, lateral_condition, drive_condition
            return height_condition and lateral_condition and drive_condition

##### /END CONDITIONS #########################################################

    def run(self, condition=None):
        # Default condition to something sensible
        condition = condition if condition else self.simulation_run_condition

        simulation_time_current = 0
        simulation_time_previous = 0  # ms
        cost = 0.0
        ok = True

        # Setup V-REP streaming
        simxGetObjectOrientation(self.client, self.body, -1, simx_opmode_streaming)
        simxGetObjectVelocity(self.client, self.body, simx_opmode_streaming)
        simxGetObjectPosition(self.client, self.body, -1, simx_opmode_streaming)

        while ok and simxGetConnectionId(self.client) != -1:
            simxPauseCommunication(self.client, True)
            err_rot, euler_angles = simxGetObjectOrientation(self.client, self.body, -1, simx_opmode_buffer)
            err_vel, lin_vel, rot_vel = simxGetObjectVelocity(self.client, self.body, simx_opmode_buffer)
            err_pos, position = simxGetObjectPosition(self.client, self.body, -1, simx_opmode_buffer)
            simxPauseCommunication(self.client, False)

            err = err_rot or err_vel or err_pos
            if err > 1:
                print "-- No data right now!"
                continue

            # Check whether new commands have been executed
            simulation_time_current = simxGetLastCmdTime(self.client)
            if simulation_time_previous == simulation_time_current:
                continue
            # Calculate dt now that we have times available
            dt = simulation_time_current - simulation_time_previous
            # Store the time spent until last fetch'd value
            simulation_time_previous = simulation_time_current

            # Calculate and set control. Pitch is the angle we're primarily
            # interested in for balance control
            roll, pitch, yaw = euler_angles
            droll, dpitch, dyaw = rot_vel
            vx, vy, vz = lin_vel
            x, y, z = position
            control = self.balance_controller.control(pitch, dt)
            self.set_target_velocities(control, control)
            e = self.balance_controller.reference - pitch

            # Calculcate the cost (abs(ref-val))
            cost += e**2 + ((pi/2)*x)**2  # pi/2 # + vy**2

            # Check for continuing
            ok = condition(simulation_time_current, position)  # lin_vel, rot_vel

        return (log10(cost / max(simulation_time_current, 1)**2), simulation_time_current)


# log(self.client, 'Euler angles: ' + str(euler_angles))
# log(self.client, 'Control value: ' + str(control))
# log(self.client, 'Cost on cycle: ' + str(cost))
# log(self.client, 'Cost (final): ' + str(cost))
# log(self.client, 'Cost (final 2): ' + str(cost / niterations))

if __name__ == '__main__':
    print '-- Please use simulation.py instead!'
