multiply(int, int, bool&):
        addi    sp,sp,-48
        sw      ra,44(sp)
        sw      s0,40(sp)
        addi    s0,sp,48
        sw      a0,-36(s0)
        sw      a1,-40(s0)
        sw      a2,-44(s0)
        sw      zero,-20(s0)
        lw      a5,-40(s0)
        srli    a5,a5,31
        sb      a5,-29(s0)
        lbu     a5,-29(s0)
        beq     a5,zero,.L2
        lw      a5,-40(s0)
        neg     a5,a5
        sw      a5,-24(s0)
        j       .L3
.L2:
        lw      a5,-40(s0)
        sw      a5,-24(s0)
.L3:
        sw      zero,-28(s0)
        j       .L4
.L7:
        lw      a4,-20(s0)
        lw      a5,-36(s0)
        add     a5,a4,a5
        sw      a5,-20(s0)
        lw      a4,-20(s0)
        li      a5,32768
        bge     a4,a5,.L5
        lw      a4,-20(s0)
        li      a5,-32768
        bge     a4,a5,.L6
.L5:
        lw      a5,-44(s0)
        li      a4,1
        sb      a4,0(a5)
.L6:
        lw      a5,-28(s0)
        addi    a5,a5,1
        sw      a5,-28(s0)
.L4:
        lw      a4,-28(s0)
        lw      a5,-24(s0)
        blt     a4,a5,.L7
        lbu     a5,-29(s0)
        beq     a5,zero,.L8
        lw      a5,-20(s0)
        neg     a5,a5
        j       .L10
.L8:
        lw      a5,-20(s0)
.L10:
        mv      a0,a5
        lw      ra,44(sp)
        lw      s0,40(sp)
        addi    sp,sp,48
        jr      ra