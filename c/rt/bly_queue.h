/* bly_queue.h: queue[T], a ring buffer. Define G_NAME, G_T, G_X. */
#define F(x) BLY_CAT(G_NAME, x)
typedef struct G_NAME { u32 head, n, cap, ver; G_T *a; } G_NAME;
static G_NAME *F(_new)(i64 cap, int l) {
    G_NAME *x = (G_NAME *)bly_alloc(sizeof(G_NAME), l);
    x->cap = bly_capacity(cap, "queue", l);
    x->a = (G_T *)bly_alloc(x->cap * sizeof(G_T), l);
    return x;
}
static void F(_put)(G_NAME *x, G_T v, int l) {
    if (x->n >= x->cap) { bly_pr_cstr("queue full ("); bly_pr_int(x->cap); bly_fail(")", l); }
    x->a[(x->head + x->n++) % x->cap] = v;
    x->ver++;
}
static G_T F(_get)(G_NAME *x, int l) {
    if (!x->n) bly_fail("queue empty", l);
    G_T v = x->a[x->head];
    x->head = (x->head + 1) % x->cap;
    x->n--;
    x->ver++;
    return v;
}
static G_T F(_at)(G_NAME *x, u32 i) { return x->a[(x->head + i) % x->cap]; }
#undef F
#undef G_NAME
#undef G_T
#undef G_X
