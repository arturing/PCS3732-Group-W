factorial(int, bool&):
        addi    sp,sp,-48
        sw      ra,44(sp)
        sw      s0,40(sp)
        addi    s0,sp,48
        sw      a0,-36(s0)
        sw      a1,-40(s0)
        lw      a4,-36(s0)
        li      a5,1
        bgt     a4,a5,.L2
        li      a5,1
        j       .L3
.L2:
        li      a5,1
        sw      a5,-20(s0)
        li      a5,2
        sw      a5,-24(s0)
        j       .L4
.L6:
        lw      a4,-20(s0)
        lw      a5,-24(s0)
        mul     a5,a4,a5
        sw      a5,-20(s0)
        lw      a4,-20(s0)
        li      a5,32768
        blt     a4,a5,.L5
        lw      a5,-40(s0)
        li      a4,1
        sb      a4,0(a5)
.L5:
        lw      a5,-24(s0)
        addi    a5,a5,1
        sw      a5,-24(s0)
.L4:
        lw      a4,-24(s0)
        lw      a5,-36(s0)
        ble     a4,a5,.L6
        lw      a5,-20(s0)
.L3:
        mv      a0,a5
        lw      ra,44(sp)
        lw      s0,40(sp)
        addi    sp,sp,48
        jr      ra