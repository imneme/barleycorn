/* bly_heap.h: heap[T], a binary min-heap ordered by bly_cmp_<X>. Define G_NAME, G_T, G_X. */
#define F(x) BLY_CAT(G_NAME, x)
#define CMP BLY_CAT(bly_cmp_, G_X)
typedef struct G_NAME { u32 n, cap, ver; G_T *a; } G_NAME;
static G_NAME *F(_new)(i64 cap, int l) {
    G_NAME *x = (G_NAME *)bly_alloc(sizeof(G_NAME), l);
    x->cap = bly_capacity(cap, "heap", l);
    x->a = (G_T *)bly_alloc(x->cap * sizeof(G_T), l);
    return x;
}
static void F(_push)(G_NAME *x, G_T v, int l) {
    if (x->n >= x->cap) { bly_pr_cstr("heap full ("); bly_pr_int(x->cap); bly_fail(")", l); }
    u32 i = x->n++;
    while (i > 0 && CMP(v, x->a[(i - 1) / 2]) < 0) { x->a[i] = x->a[(i - 1) / 2]; i = (i - 1) / 2; }
    x->a[i] = v;
    x->ver++;
}
static G_T F(_pop)(G_NAME *x, int l) {
    if (!x->n) bly_fail("heap empty", l);
    G_T top = x->a[0], last = x->a[--x->n];
    u32 i = 0;
    for (;;) {
        u32 c = 2 * i + 1;
        if (c >= x->n) break;
        if (c + 1 < x->n && CMP(x->a[c + 1], x->a[c]) < 0) c++;
        if (CMP(x->a[c], last) >= 0) break;
        x->a[i] = x->a[c];
        i = c;
    }
    if (x->n) x->a[i] = last;
    x->ver++;
    return top;
}
#undef CMP
#undef F
#undef G_NAME
#undef G_T
#undef G_X
