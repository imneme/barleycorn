/* bly_list.h: list[T]. Define G_NAME (e.g. list_i16), G_T and G_X (bly_sort_<X> must exist if sort is used). */
#define F(x) BLY_CAT(G_NAME, x)
typedef struct G_NAME { u32 n, cap, ver; G_T *a; } G_NAME;
static G_NAME *F(_new)(i64 cap, int l) {
    G_NAME *x = (G_NAME *)bly_alloc(sizeof(G_NAME), l);
    x->cap = bly_capacity(cap, "list", l);
    x->a = (G_T *)bly_alloc(x->cap * sizeof(G_T), l);
    return x;
}
static void F(_push)(G_NAME *x, G_T v, int l) {
    if (x->n >= x->cap) { bly_pr_cstr("list full ("); bly_pr_int(x->cap); bly_fail(")", l); }
    x->a[x->n++] = v;
    x->ver++;
}
static G_T F(_pop)(G_NAME *x, int l) { if (!x->n) bly_fail("list empty", l); x->ver++; return x->a[--x->n]; }
static G_T F(_get)(G_NAME *x, i64 i, int l) { bly_chk_index(i, x->n, l); return x->a[i]; }
static G_T *F(_ref)(G_NAME *x, i64 i, int l) { bly_chk_index(i, x->n, l); return &x->a[i]; }
static void F(_set)(G_NAME *x, i64 i, G_T v, int l) { bly_chk_index(i, x->n, l); x->a[i] = v; }
static void F(_clear)(G_NAME *x) { x->n = 0; x->ver++; }
#ifdef G_SORTS
static void F(_sort)(G_NAME *x) { BLY_CAT(bly_sort_, G_X)(x->a, x->n); x->ver++; }
#undef G_SORTS
#endif
#undef F
#undef G_NAME
#undef G_T
#undef G_X
