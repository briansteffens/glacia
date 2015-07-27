create table functions
(
    id char(3)
,   label varchar(255)
,   return_type varchar(255)
,   arguments text

,   primary key (id)
,   unique (label)
);

create table instructions
(
    id char(3)
,   function_id char(3) null
,   parent_id char(3) null
,   previous_id char(3) null
,   code text

,   primary key (id)
,   unique (function_id, parent_id, previous_id)
,   foreign key (function_id) references functions (id)
,   foreign key (parent_id) references instructions (id)
,   foreign key (previous_id) references instructions (id)
);

create table threads
(
    id char(3)

,   primary key (id)
);

/* The call stack. Each row is a frame in a thread. */
create table calls
(
    id char(3)
,   thread_id char(3)
,   depth bigint unsigned
,   instruction_id char(3)
,   calling_instruction_id char(3) null

,   primary key (id)
,   unique (thread_id, depth)
,   foreign key (thread_id) references threads (id)
,   foreign key (instruction_id) references instructions (id)
,   foreign key (calling_instruction_id) references instructions (id)
);

/* The conditional stack. Each row is a conditional (if[/else if][/else]). */
create table conditionals
(
    call_id char(3)
,   depth int
,   satisfied bool

,   primary key (call_id, depth)
,   foreign key (call_id) references calls (id) on delete cascade
);

/* Addresses in virtual database "memory". */
create table addresses
(
    id char(3)
,   type varchar(16)
,   val varchar(255)

,   primary key (id)
);

/* Local variables visible to a given call stack frame */
create table locals
(
    id char(3)
,   call_id char(3)
,   label varchar(255)
,   address_id char(3)

,   primary key (id)
,   unique (call_id, label)
,   foreign key (call_id) references calls (id) on delete cascade
,   foreign key (address_id) references addresses (id) on delete cascade
);

/* List items */
create table items
(
    list_id char(3)
,   ordinal int
,   address_id char(3)

,   primary key (list_id, ordinal)
,   foreign key (list_id) references addresses (id) on delete cascade
,   foreign key (address_id) references addresses (id) on delete cascade
);
