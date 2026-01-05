#!/usr/bin/exec-suid -- /usr/bin/python3 -I
from sage.all import *
from Crypto.Util.number import getPrime
import signal
import sys

def _timeout(_signum, _frame):
    sys.exit(0)

def get_point_of_order(E, r, n):
    cofactor = n // r
    while True:
        P = E.random_point()
        if P == E(0):
            continue
        G = cofactor * P
        if G != E(0) and (r * G) == E(0):
            return G

def main():
    signal.signal(signal.SIGALRM, _timeout)
    flag = open('/flag', 'r').read()

    while True:
        r = getPrime(45)
        p = ZZ(4*r - 1)
        if p % 4 == 3 and p.is_prime():
            break

    Fp = GF(p)
    E = EllipticCurve(GF(p), [1, 0])
    n = E.order()
    assert E.is_supersingular()

    G = get_point_of_order(E, r, n)

    print("After meditating on Iwakeli`i, I heard a voice!")
    print("She told me the age of quantum is among us and that I shall ascend as a god to lead the charge.")
    print("Everyone knows the key to security in the post quantum age lies in the supersingularity.")
    print("And yet a challenger still dare approach me!")
    print("You must have your head in the stars if you think you can steal my shared secret 6 times in 9 minutes!")
    print("Since im so nice i'll give you the common knowledge your puny brain needs:")
    print(f'\tG = {(G[0], G[1])}')
    print(f'\tp = {p}')
    print("Your time starts NOW!\n\n")
    signal.alarm(540)
    for _ in range(6):
        a = ZZ.random_element(1, r)
        b = ZZ.random_element(1, r)
        A = a * G
        B = b * G
        S = a * B
        assert S == b * A
        print(f'A = {(A[0], A[1])}')
        print(f'B = {(B[0], B[1])}')
        guess = int(input("What say you?\n"))
        if S.xy()[0] != guess:
            print("Go back home PUNY MORTAL! You are not cut out for this realm!")
            sys.exit(0)
        print("AGAIN!\n\n")
    print("You have shown to me you are worthy!")
    print("Have this ancient relic as a reward for your skills!")
    print(flag)

if __name__ == "__main__":
    main()
