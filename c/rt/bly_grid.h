/* bly_grid.h: grid[T]. Define G_NAME, G_T, G_X (bly_eq_ and bly_pr_ for find). */
#define F(x) BLY_CAT(G_NAME, x)
typedef struct G_NAME { i32 rows, cols; G_T *a; } G_NAME;
static G_NAME *F(_new)(i64 rows, i64 cols, G_T fill, int l) {
    if (rows < 0 || cols < 0) bly_fail("a grid has no negative sides", l);
    if (rows > 32767 || cols > 32767) bly_fail("a grid side is at most 32767", l);
    G_NAME *x = (G_NAME *)bly_alloc(sizeof(G_NAME), l);
    x->rows = (i32)rows;
    x->cols = (i32)cols;
    x->a = (G_T *)bly_alloc((size_t)(rows * cols) * sizeof(G_T) + 1, l);
    for (i64 i = 0; i < rows * cols; i++) x->a[i] = fill;
    return x;
}
static void F(_chk)(G_NAME *x, i64 r, i64 c, int l) {
    if (r < 0 || r >= x->rows || c < 0 || c >= x->cols) {
        bly_pr_cstr("("); bly_pr_int(r); bly_pr_cstr(", "); bly_pr_int(c); bly_pr_cstr(") is off the grid (");
        bly_pr_int(x->rows); bly_pr_cstr(" x "); bly_pr_int(x->cols); bly_fail(")", l);
    }
}
static G_T F(_get)(G_NAME *x, i64 r, i64 c, int l) { F(_chk)(x, r, c, l); return x->a[r * x->cols + c]; }
static G_T *F(_ref)(G_NAME *x, i64 r, i64 c, int l) { F(_chk)(x, r, c, l); return &x->a[r * x->cols + c]; }
static void F(_set)(G_NAME *x, i64 r, i64 c, G_T v, int l) { F(_chk)(x, r, c, l); x->a[r * x->cols + c] = v; }
static b8 F(_has)(G_NAME *x, bly_pos p) { return p.r >= 0 && p.r < x->rows && p.c >= 0 && p.c < x->cols; }
static bly_pos F(_find)(G_NAME *x, G_T v, int l) {
    for (i32 r = 0; r < x->rows; r++)
        for (i32 c = 0; c < x->cols; c++)
            if (BLY_CAT(bly_eq_, G_X)(x->a[r * x->cols + c], v)) return bly_pos_make((i16)r, (i16)c);
    BLY_CAT(bly_pr_, G_X)(v);
    bly_fail(" is not on the grid", l);
}
#undef F
#undef G_NAME
#undef G_T
#undef G_X
